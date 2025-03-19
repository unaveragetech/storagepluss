from asyncio import Queue
import os
import shutil
from venv import logger
import psutil
import subprocess
import json
from datetime import datetime, time
import time
from pathlib import Path
from tqdm import tqdm
import humanize
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import queue
import win32com.client
import win32api
import win32con
from enum import Enum
from typing import Dict, List, Tuple, Protocol
import ctypes
from colorama import Fore, Back, Style
import re
from rich.progress import (
    Progress, 
    BarColumn, 
    TextColumn, 
    TimeRemainingColumn,
    SpinnerColumn,
    TaskID
)
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
import random
import itertools
import threading
import time
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum, auto
import hashlib

# Add these constants for protected directories
PROTECTED_DIRECTORIES = {
    'system': [
        'C:\\Windows',
        'C:\\Program Files (x86)',
        'C:\\Program Files',
        'C:\\Program Files\\WindowsApps',
        'C:\\ProgramData',
        'System32',
        'SysWOW64'
    ],
    'user_critical': [
        'AppData\\Local\\Microsoft',
        'AppData\\Roaming\\Microsoft',
        'AppData\\Local\\Programs',
        '.vscode',
        '.git'
    ],
    'system_files': [
        'pagefile.sys',
        'hiberfil.sys',
        'swapfile.sys'
    ]
}

class FilePriority(Enum):
    CRITICAL = 4    # System files, important documents
    HIGH = 3        # User data, recent files
    MEDIUM = 2      # Media files, downloads
    LOW = 1         # Temporary files, old backups
    UNKNOWN = 0

class SizeCategory(Enum):
    VERY_LARGE = 4  # > 10GB
    LARGE = 3       # 2GB - 10GB
    MEDIUM = 2      # 500MB - 2GB
    SMALL = 1       # 100MB - 500MB

class FileGroup:
    def __init__(self, path: Path, size: int, priority: FilePriority, category: SizeCategory):
        self.path = path
        self.size = size
        self.priority = priority
        self.category = category
        self.last_accessed = datetime.fromtimestamp(path.stat().st_atime)
        self.score = self._calculate_score()

    def _calculate_score(self) -> float:
        """Calculate move priority score based on size, priority, and last access"""
        size_weight = self.category.value * 0.4
        priority_weight = self.priority.value * 0.3
        days_since_access = (datetime.now() - self.last_accessed).days
        access_weight = min(days_since_access / 365, 1.0) * 0.3
        return size_weight + priority_weight + access_weight

def create_system_restore_point(description: str) -> bool:
    """Creates a system restore point on Windows.
    
    Args:
        description: Name of the restore point
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if running with admin privileges
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        if not is_admin:
            print("\n⚠️ Administrative privileges required!")
            print("Please run the script as administrator:")
            print("1. Right-click on the script")
            print("2. Select 'Run as administrator'")
            return False

        # Create restore point using PowerShell with elevated privileges
        ps_command = f'Checkpoint-Computer -Description "{description}" -RestorePointType "MODIFY_SETTINGS"'
        
        result = subprocess.run(
            ['powershell', '-Command', ps_command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode == 0:
            print(f"\n✅ Created system restore point: {description}")
            return True
            
        if "Access denied" in result.stderr:
            print("\n⚠️ Access denied while creating restore point!")
            print("Please ensure you're running the script as administrator")
            return False
            
        print(f"\n⚠️ Failed to create system restore point: {result.stderr.strip()}")
        return False
        
    except Exception as e:
        print(f"\n⚠️ Failed to create system restore point: {e}")
        return False

def analyze_and_group_files(files: List[Tuple[Path, int]]) -> Dict[SizeCategory, List[FileGroup]]:
    """Analyze files and group them by size category with priority ranking"""
    grouped_files: Dict[SizeCategory, List[FileGroup]] = {
        category: [] for category in SizeCategory
    }
    
    for file_path, size in files:
        # Determine size category
        if size > 10 * 1024**3:  # 10GB
            category = SizeCategory.VERY_LARGE
        elif size > 2 * 1024**3:  # 2GB
            category = SizeCategory.LARGE
        elif size > 500 * 1024**2:  # 500MB
            category = SizeCategory.MEDIUM
        else:
            category = SizeCategory.SMALL
        
        # Determine priority based on file type and location
        priority = determine_file_priority(file_path)
        
        # Create FileGroup object
        file_group = FileGroup(file_path, size, priority, category)
        grouped_files[category].append(file_group)
    
    # Sort each category by score
    for category in grouped_files:
        grouped_files[category].sort(key=lambda x: x.score, reverse=True)
    
    return grouped_files

def determine_file_priority(file_path: Path) -> FilePriority:
    """Determine file priority based on type and location"""
    # System directories that indicate high priority
    system_dirs = {'windows', 'program files', 'program files (x86)', 'programdata'}
    
    # Check if it's in a system directory
    if any(sys_dir.lower() in str(file_path).lower() for sys_dir in system_dirs):
        return FilePriority.CRITICAL
    
    # Check file extensions
    ext = file_path.suffix.lower()
    
    # Critical files
    if ext in {'.sys', '.dll', '.exe', '.msi', '.doc', '.docx', '.pdf'}:
        return FilePriority.CRITICAL
    
    # High priority files
    if ext in {'.psd', '.ai', '.prproj', '.aep', '.db', '.sql'}:
        return FilePriority.HIGH
    
    # Medium priority files
    if ext in {'.mp4', '.mp3', '.jpg', '.png', '.zip', '.rar'}:
        return FilePriority.MEDIUM
    
    # Low priority files
    if ext in {'.tmp', '.log', '.bak', '.old', '.temp'}:
        return FilePriority.LOW
    
    return FilePriority.UNKNOWN

def create_size_bar(size: int, total_size: int, width: int = 50) -> str:
    """Create a visual bar representing file size proportion"""
    proportion = size / total_size
    filled = int(width * proportion)
    return f"{'█' * filled}{'░' * (width - filled)}"

def format_percentage(size: int, total_size: int) -> str:
    """Format percentage with proper alignment"""
    return f"{(size / total_size) * 100:5.1f}%"

def display_grouped_files(grouped_files: Dict[SizeCategory, List[FileGroup]]) -> None:
    """Display grouped files with improved formatting and visualizations"""
    total_size = sum(sum(file.size for file in files) for files in grouped_files.values())
    
    print("\n" + "═" * 60)
    print(f"📊 File Analysis Summary │ Total: {humanize.naturalsize(total_size)}")
    print("═" * 60)
    
    # Display size distribution graph
    print("\n📈 Size Distribution:")
    print("─" * 60)
    
    # Calculate category sizes
    category_sizes = {
        category: sum(file.size for file in files)
        for category, files in grouped_files.items()
    }
    
    # Display size distribution bars
    for category in SizeCategory:
        if category not in category_sizes or not category_sizes[category]:
            continue
            
        size = category_sizes[category]
        percentage = format_percentage(size, total_size)
        bar = create_size_bar(size, total_size)
        
        print(f"{category.name:10} │ {percentage} │ {bar} │ {humanize.naturalsize(size)}")
    
    print("─" * 60)
    
    # Display priority distribution
    print("\n🎯 Priority Distribution:")
    print("─" * 60)
    
    priority_sizes = {priority: 0 for priority in FilePriority}
    for files in grouped_files.values():
        for file in files:
            priority_sizes[file.priority] += file.size
    
    for priority in FilePriority:
        if not priority_sizes[priority]:
            continue
            
        size = priority_sizes[priority]
        percentage = format_percentage(size, total_size)
        bar = create_size_bar(size, total_size)
        
        print(f"{priority.name:10} │ {percentage} │ {bar} │ {humanize.naturalsize(size)}")
    
    print("─" * 60)
    
    # Detailed file listing by category
    # Color mapping for priorities
    priority_colors = {
        FilePriority.CRITICAL: Fore.RED,
        FilePriority.HIGH: Fore.YELLOW,
        FilePriority.MEDIUM: Fore.GREEN,
        FilePriority.LOW: Fore.CYAN,
        FilePriority.UNKNOWN: Fore.WHITE
    }
    
    # Color mapping for size categories
    category_colors = {
        SizeCategory.VERY_LARGE: Back.RED,
        SizeCategory.LARGE: Back.YELLOW,
        SizeCategory.MEDIUM: Back.GREEN,
        SizeCategory.SMALL: Back.CYAN
    }

    for category in SizeCategory:
        files = grouped_files[category]
        if not files:
            continue
            
        category_size = sum(file.size for file in files)
        print(f"\n{category_colors[category]}{category.name} Files{Style.RESET_ALL} │ {humanize.naturalsize(category_size)}")
        print("─" * 50)
        
        priority_groups = {}
        for file in files:
            if file.priority not in priority_groups:
                priority_groups[file.priority] = []
            priority_groups[file.priority].append(file)
        
        sorted_priorities = sorted(priority_groups.keys(), key=lambda x: x.value, reverse=True)
        
        for priority in sorted_priorities:
            priority_files = priority_groups[priority]
            priority_size = sum(file.size for file in priority_files)
            
            print(f"\n  {priority_colors[priority]}{priority.name}{Style.RESET_ALL} ({humanize.naturalsize(priority_size)})")
            
            for idx, file in enumerate(priority_files, 1):
                percentage = format_percentage(file.size, category_size)
                bar = create_size_bar(file.size, category_size, width=30)
                
                print(f"  {'└── ' if idx == len(priority_files) else '├── '}"
                      f"{Fore.CYAN}{file.path.name}{Style.RESET_ALL}")
                print(f"      ├── Size: {humanize.naturalsize(file.size)} ({percentage})")
                print(f"      ├── Bar: {Fore.BLUE}{bar}{Style.RESET_ALL}")
                print(f"      ├── Last accessed: {file.last_accessed.strftime('%Y-%m-%d')}")
                print(f"      └── Priority score: {file.score:.2f}")
            
            if len(priority_files) > 5:
                print(f"\n      └── ... and {Fore.YELLOW}{len(priority_files) - 5} more files{Style.RESET_ALL}")
    
    # Display summary statistics
    print("\n📊 Summary Statistics:")
    print("─" * 60)
    print(f"Total Files: {sum(len(files) for files in grouped_files.values())}")
    print(f"Total Size: {humanize.naturalsize(total_size)}")
    print(f"Average File Size: {humanize.naturalsize(total_size / max(1, sum(len(files) for files in grouped_files.values())))}")
    print("─" * 60)

def select_directory(title="Select Directory"):
    """Open a directory selection dialog and return the selected path"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    root.attributes('-topmost', True)  # Bring dialog to front
    directory = filedialog.askdirectory(title=title)
    return directory if directory else None

class FileOperation:
    def __init__(self, src, dest, size=None):
        self.src = str(src)
        self.dest = str(dest)
        self.size = size if size is not None else Path(src).stat().st_size
        self.timestamp = datetime.now().isoformat()

    @classmethod
    def from_dict(cls, data):
        return cls(
            src=data['src'],
            dest=data['dest'],
            size=data['size']
        )

    def to_dict(self):
        return {
            'src': self.src,
            'dest': self.dest,
            'size': self.size,
            'timestamp': self.timestamp
        }

class OperationLogger:
    def __init__(self, log_file="file_operations.json"):
        self.log_file = log_file
        self.operations = []
        self.load_operations()

    def load_operations(self):
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    self.operations = [FileOperation.from_dict(op) for op in data]
            except json.JSONDecodeError:
                print(f"⚠️ Error reading log file: {self.log_file}")
                self.operations = []

    def save_operations(self):
        with open(self.log_file, 'w') as f:
            json.dump([op.to_dict() for op in self.operations], f, indent=2)

    def add_operation(self, src_path: Path, dest_path: Path):
        """Add a file operation to the log"""
        operation = FileOperation(
            src=str(src_path),
            dest=str(dest_path),
            timestamp=datetime.now().isoformat()
        )
        self.operations.append(operation)
        self.save_operations()

def open_file_explorer(path):
    """Open file explorer at specified path"""
    if os.name == 'nt':  # Windows
        subprocess.Popen(f'explorer "{path}"')
    elif os.name == 'posix':  # macOS and Linux
        subprocess.Popen(['xdg-open', path])

def get_disk_usage(path):
    """Get disk usage statistics for the given path
    Args:
        path: Path-like object or string path
    Returns:
        Dictionary containing total, used and free space in bytes
    """
    # Convert Path object to string if necessary
    path_str = str(path)
    usage = psutil.disk_usage(path_str)
    return {
        'total': usage.total,
        'used': usage.used,
        'free': usage.free
    }

def scan_directory(args):
    """Worker function to scan directories for large files
    Args:
        args: Tuple containing (directory_path, min_size, file_queue)
    """
    directory_path, min_size, file_queue = args
    try:
        file_path = Path(directory_path)
        if file_path.exists() and file_path.stat().st_size >= min_size:
            file_queue.put((file_path, file_path.stat().st_size))
    except PermissionError:
        pass
    except Exception as e:
        print(f"\nError scanning {directory_path}: {e}")

def list_large_files(directory, min_size=100 * 1024 * 1024, max_workers=10):
    """Find large files using parallel processing
    Args:
        directory: Path to search
        min_size: Minimum file size in bytes
        max_workers: Number of parallel threads
    Returns:
        List of tuples containing (file_path, file_size)
    """
    large_files = []
    file_queue = queue.Queue()
    
    print(f"\nScanning {directory} for files larger than {humanize.naturalsize(min_size)}...")
    print("Using parallel processing to speed up the scan...")
    
    # Collect all files first
    all_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            all_files.append(os.path.join(root, file))
    
    # Show progress bar for total files being processed
    with tqdm(total=len(all_files), desc="Scanning files", unit="files") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create tasks for each file
            scan_args = [(f, min_size, file_queue) for f in all_files]
            
            # Submit tasks and update progress
            futures = []
            for arg in scan_args:
                future = executor.submit(scan_directory, arg)
                future.add_done_callback(lambda p: pbar.update(1))
                futures.append(future)
            
            # Wait for all tasks to complete
            for future in futures:
                future.result()
    
    # Collect results from queue
    while not file_queue.empty():
        large_files.append(file_queue.get())
    
    return sorted(large_files, key=lambda x: x[1], reverse=True)

class TransferStatus(Enum):
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()

@dataclass
class TransferResult:
    success: bool
    status: TransferStatus
    error_message: str = ""
    source_size: int = 0
    dest_size: int = 0
    verified: bool = False
    src_path: Path = None  # Add source path
    dest_path: Path = None  # Add destination path

def verify_file_transfer(src_path: Path, dest_path: Path, chunk_size: int = 8192) -> bool:
    """Verify file transfer by comparing file sizes and checksums"""
    try:
        # First verify source exists and is readable
        if not src_path.exists():
            print(f"❌ Source file no longer exists: {src_path}")
            return False
            
        # Then verify destination exists
        if not dest_path.exists():
            print(f"❌ Destination file not found: {dest_path}")
            return False
            
        # Compare sizes first (quick check)
        src_size = src_path.stat().st_size
        dest_size = dest_path.stat().st_size
        
        if src_size != dest_size:
            print(f"❌ Size mismatch: Source={humanize.naturalsize(src_size)}, Dest={humanize.naturalsize(dest_size)}")
            return False
            
        # Calculate MD5 checksums
        src_hash = hashlib.md5()
        dest_hash = hashlib.md5()
        
        # Read source file
        with open(src_path, 'rb') as sf:
            while True:
                chunk = sf.read(chunk_size)
                if not chunk:
                    break
                src_hash.update(chunk)
                
        # Read destination file
        with open(dest_path, 'rb') as df:
            while True:
                chunk = df.read(chunk_size)
                if not chunk:
                    break
                dest_hash.update(chunk)
                
        # Compare hashes
        src_digest = src_hash.hexdigest()
        dest_digest = dest_hash.hexdigest()
        
        if src_digest != dest_digest:
            print(f"❌ Checksum mismatch:")
            print(f"├── Source MD5: {src_digest}")
            print(f"└── Dest MD5:   {dest_digest}")
            return False
            
        return True
        
    except PermissionError as e:
        print(f"❌ Permission error during verification: {e}")
        return False
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False

def move_file(src_path: Path, dest_dir: Path, logger: OperationLogger) -> TransferResult:
    """Move file with enhanced error handling and verification"""
    result = TransferResult(
        success=False,
        status=TransferStatus.PENDING,
        source_size=0,
        error_message="",
        src_path=src_path,  # Set source path
        dest_path=None      # Will be set later
    )
    
    try:
        # Verify source exists and get size
        if not src_path.exists():
            result.status = TransferStatus.FAILED
            result.error_message = "Source file not found"
            print(f"⚠️ File not found: {src_path}")
            return result
            
        result.source_size = src_path.stat().st_size
        
        # Check if file exists at destination
        dest_path = dest_dir / src_path.name
        if dest_path.exists():
            print(f"⚠️ Destination file already exists: {dest_path}")
            new_name = f"{src_path.stem}_{int(time.time())}{src_path.suffix}"
            dest_path = dest_dir / new_name
            print(f"Trying alternative name: {new_name}")
        
        result.dest_path = dest_path  # Set destination path
        
        # Verify source is readable before moving
        try:
            with open(src_path, 'rb') as f:
                # Read first chunk to verify access
                f.read(1)
        except PermissionError:
            result.status = TransferStatus.FAILED
            result.error_message = "Source file is locked or in use"
            print(f"⚠️ File is locked or in use: {src_path}")
            return result
            
        result.status = TransferStatus.IN_PROGRESS
        print(f"\n📦 Transferring: {src_path.name}")
        print(f"├── Source: {src_path}")
        print(f"└── Destination: {dest_path}")
        
        # Copy first, then delete source if successful
        shutil.copy2(str(src_path), str(dest_path))
        
        # Verify the copy
        if verify_file_transfer(src_path, dest_path):
            # Only delete source after successful verification
            os.remove(str(src_path))
            
            result.dest_size = dest_path.stat().st_size
            result.verified = True
            result.status = TransferStatus.COMPLETED
            result.success = True
            
            print(f"✅ Transfer successful and verified:")
            print(f"├── Size: {humanize.naturalsize(result.dest_size)}")
            print(f"└── Location: {dest_path}")
            
            # Log the operation
            operation = FileOperation(src_path, dest_path, result.dest_size)
            logger.operations.append(operation)
            logger.save_operations()
        else:
            # Clean up failed copy
            if dest_path.exists():
                try:
                    os.remove(str(dest_path))
                except Exception as e:
                    print(f"⚠️ Failed to clean up incomplete transfer: {e}")
                    
            result.status = TransferStatus.FAILED
            result.error_message = "Transfer verification failed"
            print(f"❌ Transfer verification failed: {src_path.name}")
            
    except PermissionError as e:
        result.status = TransferStatus.FAILED
        result.error_message = f"Permission denied: {str(e)}"
        print(f"⚠️ Permission denied: {src_path}")
    except FileNotFoundError as e:
        result.status = TransferStatus.FAILED
        result.error_message = f"File not found: {str(e)}"
        print(f"⚠️ File not found: {src_path}")
    except Exception as e:
        result.status = TransferStatus.FAILED
        result.error_message = f"Unexpected error: {str(e)}"
        print(f"⚠️ Unexpected error: {e}")
        
    return result

def revert_operations(logger):
    print("\nReverting operations...")
    success_count = 0
    fail_count = 0
    
    with tqdm(total=len(logger.operations), desc="Reverting") as pbar:
        for operation in reversed(logger.operations):
            try:
                src = Path(operation.src)
                dest = Path(operation.dest)
                if dest.exists() and not src.exists():
                    shutil.move(str(dest), str(src))
                    success_count += 1
                pbar.update(1)
            except Exception as e:
                print(f"\nError reverting {dest}: {e}")
                fail_count += 1
    
    print(f"\nRevert complete: {success_count} successful, {fail_count} failed")
    if success_count > 0:
        logger.operations = logger.operations[:-success_count]
        logger.save_operations()

def display_file_info(files):
    """Display information about found files with improved formatting
    Args:
        files: List of tuples containing (file_path, file_size)
    """
    if not files:
        print("\nNo large files found!")
        return
    
    total_size = sum(size for _, size in files)
    print(f"\nFound {len(files)} large files (Total: {humanize.naturalsize(total_size)})")
    print("\nTop 10 largest files:")
    for file, size in files[:10]:
        print(f"├── {file.name}")
        print(f"│   ├── Size: {humanize.naturalsize(size)}")
        print(f"│   └── Path: {file.parent}")
    
    if len(files) > 10:
        print(f"└── ... and {len(files) - 10} more files")

class SmartFileAssistant:
    def __init__(self):
        self.system_directories = {
            'windows': ['Windows', 'Program Files', 'Program Files (x86)', 'ProgramData'],
            'user_critical': ['AppData\\Local\\Microsoft', 'AppData\\Roaming\\Microsoft'],
            'safe_to_move': ['Downloads', 'Documents', 'Pictures', 'Music', 'Videos', 'Desktop']
        }
        
        self.file_categories = {
            'media': ['.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.flac'],
            'documents': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'],
            'archives': ['.zip', '.rar', '.7z', '.tar', '.gz'],
            'installers': ['.exe', '.msi', '.iso'],
            'games': ['.exe', '.dll', '.pak', '.unity3d'],
        }
        
        self.size_ranges = {
            'small': (100 * 1024 * 1024, 500 * 1024 * 1024),      # 100MB - 500MB
            'medium': (500 * 1024 * 1024, 2 * 1024 * 1024 * 1024), # 500MB - 2GB
            'large': (2 * 1024 * 1024 * 1024, float('inf'))        # 2GB+
        }

    def analyze_file(self, file_path: Path) -> dict:
        """Analyze a file and return its characteristics"""
        stats = {
            'category': 'unknown',
            'is_system_file': False,
            'last_accessed': None,
            'size_category': 'unknown',
            'safe_to_move': False,
            'recommendation': None
        }
        
        try:
            # Get file information
            size = file_path.stat().st_size
            last_access = datetime.fromtimestamp(file_path.stat().st_atime)
            extension = file_path.suffix.lower()
            
            # Determine category
            for category, extensions in self.file_categories.items():
                if extension in extensions:
                    stats['category'] = category
                    break
            
            # Determine size category
            for size_cat, (min_size, max_size) in self.size_ranges.items():
                if min_size <= size < max_size:
                    stats['size_category'] = size_cat
                    break
            
            # Check if it's a system file
            for sys_dir in self.system_directories['windows']:
                if sys_dir.lower() in str(file_path).lower():
                    stats['is_system_file'] = True
                    break
            
            # Check if it's safe to move
            stats['safe_to_move'] = (
                not stats['is_system_file'] and
                any(safe_dir.lower() in str(file_path).lower() 
                    for safe_dir in self.system_directories['safe_to_move'])
            )
            
            # Generate recommendation
            stats['recommendation'] = self._generate_recommendation(stats, last_access)
            stats['last_accessed'] = last_access
            
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
        
        return stats

    def _generate_recommendation(self, stats: dict, last_access: datetime) -> str:
        """Generate a recommendation based on file analysis"""
        now = datetime.now()
        days_since_access = (now - last_access).days
        
        if stats['is_system_file']:
            return "Keep - System File"
        
        if stats['category'] == 'media' and days_since_access > 30:
            return "Safe to Move - Media file not accessed in over 30 days"
        
        if stats['category'] == 'installers':
            return "Consider Moving - Installation file can be downloaded again if needed"
        
        if stats['size_category'] == 'large' and days_since_access > 60:
            return "Consider Moving - Large file not accessed in over 60 days"
        
        return "Review - No specific recommendation"

def is_protected_path(path: Path) -> bool:
    """Check if a path is protected"""
    path_str = str(path).lower()
    file_name = path.name.lower()
    
    # Immediate return for system files
    if file_name in [f.lower() for f in PROTECTED_DIRECTORIES['system_files']]:
        return True
    
    # Check system directories
    for sys_dir in PROTECTED_DIRECTORIES['system']:
        if sys_dir.lower() in path_str:
            return True
    
    # Check user critical directories
    for critical_dir in PROTECTED_DIRECTORIES['user_critical']:
        if critical_dir.lower() in path_str:
            return True
    
    # Additional system file patterns
    system_patterns = [
        r'C:\\pagefile.sys',
        r'C:\\hiberfil.sys',
        r'C:\\swapfile.sys',
        r'C:\\Windows\\.*',
        r'C:\\Program Files\\.*',
        r'C:\\Program Files (x86)\\.*',
        r'C:\\ProgramData\\.*',
    ]
    
    for pattern in system_patterns:
        if re.match(pattern, path_str, re.IGNORECASE):
            return True
            
    return False

def get_optimal_worker_count() -> dict:
    """
    Determines the optimal worker count range based on CPU architecture.
    Returns a dictionary with CPU info and recommended workers.
    """
    try:
        physical_cores = psutil.cpu_count(logical=False)
        logical_processors = psutil.cpu_count(logical=True)
        
        if not physical_cores or not logical_processors:
            return {
                'physical_cores': None,
                'logical_processors': None,
                'recommended': 10,
                'min': 4,
                'max': 32,
                'absolute_max': 48
            }
            
        # Calculate recommended workers
        if logical_processors > physical_cores:
            # CPU has hyperthreading/SMT
            recommended = max(physical_cores, int(logical_processors * 0.75))
        else:
            recommended = physical_cores
            
        return {
            'physical_cores': physical_cores,
            'logical_processors': logical_processors,
            'recommended': recommended,
            'min': max(2, physical_cores // 2),
            'max': logical_processors,
            'absolute_max': logical_processors * 2,  # Allow up to 2x logical processors
            'has_hyperthreading': logical_processors > physical_cores
        }
        
    except Exception as e:
        print(f"\nWarning: Could not determine CPU configuration: {e}")
        return {
            'physical_cores': None,
            'logical_processors': None,
            'recommended': 10,
            'min': 4,
            'max': 32,
            'absolute_max': 48
        }

class ScanningAnimation:
    def __init__(self):
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.is_running = False
        self.stats: Dict[str, int] = {
            "files_found": 0,
            "dirs_scanned": 0,
            "total_size": 0
        }
        self._lock = threading.Lock()

    def update_stats(self, files: int = 0, dirs: int = 0, size: int = 0):
        with self._lock:
            self.stats["files_found"] += files
            self.stats["dirs_scanned"] += dirs
            self.stats["total_size"] += size

    def _animate(self):
        spinner = itertools.cycle(self.spinner_chars)
        while self.is_running:
            with self._lock:
                stats = self.stats.copy()
            
            print(f"\r\033[K\033[F\033[K\033[F\033[K", end="")  # Clear previous lines
            print(f"\r🔍 Scanning System {next(spinner)}")
            print(f"├── Directories Scanned: {stats['dirs_scanned']:,}")
            print(f"├── Files Found: {stats['files_found']:,}")
            print(f"└── Total Size: {humanize.naturalsize(stats['total_size'])}")
            time.sleep(0.1)

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._animate)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if hasattr(self, 'thread'):
            self.thread.join()
        print("\n✨ Scan Complete!")

class WorkerProgress(Protocol):
    def update_stats(self, files: int = 0, size: int = 0, dirs: int = 0) -> None: ...
    def update_worker(self, worker_id: int, progress: float) -> None: ...

def scan_worker(
    worker_id: int,
    directory: Path,
    queue: Queue,
    progress: WorkerProgress,
    min_size: int
):
    """Individual worker process for scanning"""
    for root, dirs, files in os.walk(str(directory)):
        root_path = Path(root)
        
        if is_protected_path(root_path):
            dirs.clear()
            continue
        
        files_found = 0
        total_size = 0
        
        for file in files:
            file_path = root_path / file
            try:
                if file_path.is_file():
                    size = file_path.stat().st_size
                    if size >= min_size:
                        queue.put((file_path, size))
                        files_found += 1
                        total_size += size
            except (PermissionError, FileNotFoundError):
                continue
        
        progress.update_stats(
            files=files_found,
            size=total_size,
            dirs=1
        )
        # Simulate some work for visual effect
        progress.update_worker(worker_id, random.uniform(0.1, 1.0))

def smart_scan_directory(
    directory: Path,
    min_size: int = 100 * 1024 * 1024,
    max_workers: int = None
) -> List[Tuple[Path, int]]:
    """Smart scan directory with rich progress display"""
    
    if max_workers is None:
        max_workers = os.cpu_count() or 4
        
    large_files = []
    file_queue = queue.Queue()
    
    console = Console()
    
    # Get initial directory count for progress
    total_dirs = sum(1 for _ in os.walk(str(directory)))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TimeRemainingColumn(),
        TextColumn("{task.fields[current_file]}"),
        console=console,
        expand=True,
        refresh_per_second=15  # Increase refresh rate for smoother updates
    ) as progress:
        # Create main scanning task
        main_task = progress.add_task(
            f"[yellow]Scanning {directory}...", 
            total=total_dirs,
            current_file=""
        )
        
        # Create tasks for each worker
        worker_tasks = [
            progress.add_task(
                f"[cyan]Worker {i+1}", 
                total=100,
                current_file=""
            ) for i in range(max_workers)
        ]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            
            for root, _, files in os.walk(str(directory)):
                root_path = Path(root)
                
                if is_protected_path(root_path):
                    progress.update(main_task, advance=1)
                    continue
                
                # Submit directory scan task to thread pool
                future = executor.submit(
                    scan_directory_chunk,
                    root_path,
                    files,
                    min_size,
                    file_queue,
                    progress,
                    worker_tasks[len(futures) % max_workers]
                )
                futures.append(future)
                
                progress.update(main_task, advance=1)
            
            # Wait for all futures to complete
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    console.print(f"[red]Error scanning directory: {e}")
    
    # Collect results from queue
    while not file_queue.empty():
        large_files.append(file_queue.get())
    
    return sorted(large_files, key=lambda x: x[1], reverse=True)

def scan_directory_chunk(
    root_path: Path,
    files: List[str],
    min_size: int,
    file_queue: queue.Queue,
    progress: Progress,
    worker_task_id: TaskID
) -> None:
    """Scan a chunk of files in a directory"""
    try:
        for file in files:
            file_path = root_path / file
            try:
                # Update worker's current file
                progress.update(
                    worker_task_id,
                    current_file=f"[dim]{file_path.name[:30]}{'...' if len(file_path.name) > 30 else ''}"
                )
                
                if file_path.is_file():
                    size = file_path.stat().st_size
                    if size >= min_size:
                        file_queue.put((file_path, size))
                        
                # Update progress
                progress.update(
                    worker_task_id,
                    completed=random.randint(0, 100)
                )
                
            except (PermissionError, FileNotFoundError):
                continue
                
    except Exception as e:
        print(f"Error scanning {root_path}: {e}")
    finally:
        # Clear the current file and show completion
        progress.update(
            worker_task_id,
            completed=100,
            current_file="[green]Done"
        )

def analyze_file(file_path: Path, min_size: int, file_queue: queue.Queue) -> None:
    """Analyze a single file and add to queue if it meets criteria
    
    Args:
        file_path: Path to the file
        min_size: Minimum file size in bytes
        file_queue: Queue to store results
    """
    try:
        # Skip if it's a protected path
        if is_protected_path(file_path):
            return
            
        # Get file stats
        stats = file_path.stat()
        
        # Check size and add to queue
        if stats.st_size >= min_size:
            file_queue.put((file_path, stats.st_size))
            
    except (PermissionError, FileNotFoundError):
        pass
    except Exception as e:
        print(f"\nError analyzing {file_path}: {e}")

def display_smart_analysis(results: list):
    """Display smart analysis results with categories"""
    if not results:
        print("\nNo suitable files found for moving!")
        return
    
    total_size = sum(file_path.stat().st_size for file_path, _ in results)
    
    print(f"\n📊 Smart Analysis Results")
    print(f"Found {len(results)} files that can be safely moved (Total: {humanize.naturalsize(total_size)})")
    
    # Group by category
    categories = {}
    for file_path, analysis in results:
        cat = analysis['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((file_path, analysis))
    
    # Display by category
    for category, files in categories.items():
        cat_size = sum(file_path.stat().st_size for file_path, _ in files)
        print(f"\n📁 {category.title()} Files ({humanize.naturalsize(cat_size)})")
        
        for file_path, analysis in sorted(files, key=lambda x: x[0].stat().st_size, reverse=True)[:5]:
            size = file_path.stat().st_size
            print(f"├── {file_path.name}")
            print(f"│   ├── Size: {humanize.naturalsize(size)}")
            print(f"│   ├── Last accessed: {analysis['last_accessed'].strftime('%Y-%m-%d')}")
            print(f"│   └── Recommendation: {analysis['recommendation']}")

class SmartModeManager:
    def __init__(self, target_dir: Path, check_interval: int = 3600):  # Default 1 hour interval
        self.check_interval = check_interval
        self.last_check = None
        self.processed_files = set()
        self.restore_point_counter = 0
        self.target_dir = target_dir

    def should_create_restore_point(self) -> bool:
        """Determine if we should create a new restore point"""
        return self.restore_point_counter % 10 == 0  # Every 10 file operations

    def process_files(self, grouped_files: Dict[SizeCategory, List[FileGroup]]) -> None:
        """Process files in smart mode"""
        current_time = datetime.now()
        logger = OperationLogger()
        
        if self.last_check and (current_time - self.last_check).total_seconds() < self.check_interval:
            return

        self.last_check = current_time
        
        # Filter and sort files
        all_files = []
        for category_files in grouped_files.values():
            for file in category_files:
                # Skip system files and already processed files
                if (not is_protected_path(file.path) and 
                    str(file.path) not in self.processed_files and
                    file.path.name.lower() not in [f.lower() for f in PROTECTED_DIRECTORIES['system_files']]):
                    all_files.append(file)
        
        # Sort by priority score
        all_files.sort(key=lambda x: x.score, reverse=True)
        
        if not all_files:
            print("\n📝 No eligible files to process")
            return
        
        print("\n🤖 Smart Mode Active - Processing Files...")
        print("═" * 60)

        total_processed = 0
        total_size_processed = 0

        transfer_results = []  # Initialize the list
        for file in all_files:
            print(f"\n📝 Processing: {file.path.name}")
            print(f"├── Size: {humanize.naturalsize(file.size)}")
            print(f"├── Priority Score: {file.score:.2f}")
            print(f"├── Category: {file.category.name}")
            print(f"└── Priority: {file.priority.name}")
            
            # Check destination space before transfer
            dest_usage = get_disk_usage(self.target_dir)
            if dest_usage['free'] < file.size:
                print(f"\n⚠️ Not enough space on target drive for {file.path.name}")
                print(f"Required: {humanize.naturalsize(file.size)}")
                print(f"Available: {humanize.naturalsize(dest_usage['free'])}")
                continue
                
            result = move_file(file.path, self.target_dir, logger)
            transfer_results.append(result)
            
            if result.success:
                total_processed += 1
                total_size_processed += result.dest_size
                self.processed_files.add(str(file.path))
            
            # Show running total
            print(f"\n📊 Progress Summary:")
            print(f"├── Files Processed: {total_processed}")
            print(f"└── Total Size Moved: {humanize.naturalsize(total_size_processed)}")
            
            time.sleep(1)
        
        # Display final summary
        display_transfer_summary(transfer_results)

def display_transfer_summary(transfer_results):
    """Display a summary of file transfer results"""
    if not transfer_results:
        print("\nNo files were transferred.")
        return

    total_files = len(transfer_results)
    total_size = sum(result.dest_size for result in transfer_results if result.success)
    success_count = sum(1 for result in transfer_results if result.success)
    failure_count = total_files - success_count

    print("\n═" * 60)
    print(f"🎉 Transfer Summary")
    print(f"├── Total Files: {total_files}")
    print(f"├── Total Size Transferred: {humanize.naturalsize(total_size)}")
    print(f"├── Successful Transfers: {success_count}")
    print(f"└── Failed Transfers: {failure_count}")

    if failure_count > 0:
        print("\nFailed Transfers:")
        for result in transfer_results:
            if not result.success:
                print(f"├── {result.source_size} ({humanize.naturalsize(result.source_size)})")
                print(f"│   ├── Source: {result.src_path}")
                if result.dest_path:
                    print(f"│   ├── Destination: {result.dest_path}")
                print(f"│   └── Error: {result.error_message}")
        print("└── End of failed transfers")

def main():
    print("\n=== Smart Storage Manager ===")
    print("This utility helps you safely manage your storage by identifying and moving non-critical files.")
    print("It uses AI-assisted analysis to ensure system stability.")
    
    # Display protected directories
    print("\n🛡️ Protected System Directories (will not be touched):")
    protected_dirs = [
        "C:\\Windows",
        "C:\\Program Files (x86)",
        "C:\\Program Files",
        "C:\\Program Files\\WindowsApps",
        "C:\\ProgramData",
        "%USERPROFILE%\\AppData",
        "System32"
    ]
    for dir in protected_dirs:
        print(f"  • {dir}")
    
    print("\n📊 File Size Categories:")
    size_ranges = [
        ("Small", "100MB - 500MB", "Good candidates for compression"),
        ("Medium", "500MB - 2GB", "Consider moving to external storage"),
        ("Large", "2GB - 10GB", "High-priority targets for cleanup"),
        ("Very Large", "10GB+", "Critical space impact - immediate action recommended")
    ]
    for category, range, desc in size_ranges:
        print(f"  • {category:<10} │ {range:<12} │ {desc}")

    # Initialize smart assistant
    assistant = SmartFileAssistant()
    
    # Select source directory
    print("\n📂 Please select the source directory (where to search for large files)...")
    source_dir = select_directory("Select Source Directory")
    if not source_dir:
        print("No source directory selected. Exiting...")
        return

    # Select target directory
    print("\n🎯 Please select the target directory (where to move the files)...")
    target_dir = select_directory("Select Target Directory")
    if not target_dir:
        print("No target directory selected. Exiting...")
        return

    # Convert to Path objects
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    
    logger = OperationLogger()
    
    print("\n=== 💾 Disk Space Analysis ===")
    try:
        src_usage = get_disk_usage(source_dir)
        dest_usage = get_disk_usage(target_dir)
        
        # Calculate available space and usage metrics
        src_free_percent = (src_usage['free'] / src_usage['total']) * 100
        dest_free_percent = (dest_usage['free'] / dest_usage['total']) * 100
        
        # Create visual bar for disk usage
        def create_usage_bar(used_percent, width=30):
            filled = int(used_percent * width / 100)
            return f"[{'█' * filled}{'░' * (width - filled)}]"
        
        src_bar = create_usage_bar(100 - src_free_percent)
        dest_bar = create_usage_bar(100 - dest_free_percent)
        
        print(f"\n📀 Source Drive ({source_dir})")
        print(f"├── Total: {humanize.naturalsize(src_usage['total'])}")
        print(f"├── Used:  {humanize.naturalsize(src_usage['used'])} ({100 - src_free_percent:.1f}%)")
        print(f"├── Free:  {humanize.naturalsize(src_usage['free'])} ({src_free_percent:.1f}%)")
        print(f"└── Usage: {src_bar}")
        
        print(f"\n💿 Target Drive ({target_dir})")
        print(f"├── Total: {humanize.naturalsize(dest_usage['total'])}")
        print(f"├── Used:  {humanize.naturalsize(dest_usage['used'])} ({100 - dest_free_percent:.1f}%)")
        print(f"├── Free:  {humanize.naturalsize(dest_usage['free'])} ({dest_free_percent:.1f}%)")
        print(f"└── Usage: {dest_bar}")
        
        # Add space efficiency recommendations
        if src_free_percent < 10:
            print("\n⚠️ WARNING: Source drive is critically low on space!")
            print("  Recommended actions:")
            print("  • Move large media files to external storage")
            print("  • Clean up downloads folder")
            print("  • Run disk cleanup utility")
        elif src_free_percent < 20:
            print("\n⚡ Notice: Source drive is running low on space")
            print("  Consider freeing up space soon")
        
    except Exception as e:
        print(f"Error accessing drives: {e}")
        return
    
    # Warn if target drive is low on space
    if dest_usage['free'] < 10 * 1024**3:  # Less than 10GB
        print("\n⚠️ Warning: Less than 10GB available on target drive!")
        response = input("Continue anyway? (yes/no): ").lower()
        if response != 'yes':
            return
    
    # Open file explorers for visual reference
    print("\n🔍 Opening file explorers for visual reference...")
    open_file_explorer(str(source_dir))
    open_file_explorer(str(target_dir))
    
    # Get file size range from user with better explanation
    print("\n📏 File Size Selection")
    print("Recommended ranges:")
    print("  • Small files:      0.1 GB - 0.5 GB")
    print("  • Medium files:     0.5 GB - 2.0 GB")
    print("  • Large files:      2.0 GB - 10.0 GB")
    print("  • Very large files: 10.0 GB and above")
    print("\nExample ranges:")
    print("  • 0.1 - 1.0: Focus on smaller files")
    print("  • 1.0 - 5.0: Focus on medium-sized files")
    print("  • 5.0 - inf: Focus on large files only")
    
    while True:
        try:
            min_size_gb = float(input("\nEnter minimum file size in GB (default is 0.1): ") or "0.1")
            max_size_input = input("Enter maximum file size in GB (press Enter for no limit): ").strip()
            max_size_gb = float(max_size_input) if max_size_input else float('inf')
            
            if min_size_gb < 0 or (max_size_input and max_size_gb < min_size_gb):
                print("❌ Invalid range! Maximum size must be greater than minimum size.")
                continue
            
            min_size = min_size_gb * 1024**3  # Convert GB to bytes
            max_size = max_size_gb * 1024**3 if max_size_gb != float('inf') else float('inf')
            
            # Display selected range
            max_size_display = f"{max_size_gb:.1f} GB" if max_size_gb != float('inf') else "∞"
            print(f"\n📊 Selected size range: {min_size_gb:.1f} GB - {max_size_display}")
            
            # Show what to expect
            if min_size_gb < 0.5:
                print("ℹ️ Including small files - might find many results")
            elif min_size_gb > 5:
                print("ℹ️ Looking for very large files only")
            
            break
        except ValueError:
            print("❌ Please enter valid numbers!")

    # Create system restore point before proceeding
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    restore_point_desc = f"LargeFileMover_Backup_{timestamp}"
    
    print("\n📦 Creating system restore point before proceeding...")
    if not create_system_restore_point(restore_point_desc):
        response = input("\nSystem restore point creation failed. Continue anyway? (yes/no): ").lower()
        if response != 'yes':
            print("Operation cancelled.")
            return

    # Smart scan for large files
    print("\n🔍 Starting smart file scan...")
    files_to_move = smart_scan_directory(
        directory=source_dir,
        min_size=min_size,  # Already in bytes from previous conversion
    )  # Let it auto-determine worker count
    
    # Analyze and group files
    grouped_files = analyze_and_group_files(files_to_move)
    
    # Display grouped files
    display_grouped_files(grouped_files)
    
    # Modified confirmation prompt to include smart mode
    while True:
        response = input("\nProceed with file transfer? (yes/no/smart): ").lower()
        if response in {'yes', 'no', 'smart'}:
            break
        print("Invalid input. Please enter 'yes', 'no', or 'smart'")

    if response == 'no':
        print("Operation cancelled.")
        return
    elif response == 'smart':
        smart_manager = SmartModeManager(target_dir=target_dir)
        smart_manager.process_files(grouped_files)
        return
    
    # Original 'yes' flow continues here
    print(f"\nMoving {len(files_to_move)} files...")
    with tqdm(
        total=sum(size for _, size in files_to_move),
        desc="📦 Moving files",
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
        bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]{postfix}'
    ) as pbar:
        for file, size in files_to_move:
            if dest_usage['free'] > size:
                if move_file(file, target_dir, logger):
                    dest_usage['free'] -= size
                    moved_size += size
                    pbar.set_postfix_str(f"Current: {file.name}")
                    pbar.update(size)
            else:
                print("\n⚠️  Target drive is full!")
                break
    
    print(f"\n✅ Moved {humanize.naturalsize(moved_size)} of data")
    
    # Offer option to revert changes
    response = input("\nDo you want to revert all operations? (yes/no): ").lower()
    if response == 'yes':
        revert_operations(logger)

if __name__ == "__main__":
    main()
