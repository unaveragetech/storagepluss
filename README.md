# 🚀 Storagepluss

**Storagepluss** is a CLI-based utility designed to help you reclaim disk space safely and efficiently. Traditional methods of freeing up space often yield minimal results or come with risks when moving files manually. Storagepluss was created with **safety as a cornerstone**, ensuring crucial directories remain intact while intelligently transferring large, non-critical files from one drive to another.

---

## 📖 Origin Story

💾 _"It all started when my C drive was nearly full, leaving me with only about 5GB of free space. I knew something had to change. Traditional cleanup methods barely made a dent, and manually moving files had caused issues in the past. I needed a reliable way to free up space without breaking anything."_

🔄 _"With this goal in mind, I set out to create a simple yet effective tool—one that could take files from Drive A, move them to Drive B, and ensure system integrity throughout the process. By detecting crucial directories and safely triaging less critical files, the tool successfully transferred over **200GB** while maintaining system backups at every step. Ultimately, it freed my C drive from the stranglehold of accumulated clutter and average use, restoring efficiency and stability."_

---

## ✨ Features

✅ **System Backup Integration** - Maintains and ensures a system backup throughout each step of the transfer process.  
✅ **Smart File Detection** - Identifies and prioritizes large files for transfer while preserving critical system directories.  
✅ **Safe and Reliable Transfers** - Moves files from Drive A to Drive B without breaking system functionality.  
✅ **Automated Logging** - Keeps detailed records of moved files, their original locations, and timestamps.  
✅ **Efficient Space Reclamation** - Frees up significant disk space with minimal user intervention.  

---

## 🔧 Installation

To install the necessary dependencies, run:

```bash
pip install -r requirements.txt
```

---

## 🚀 Usage

### 🏁 Running the Main Script

To execute the main script, use:

```bash
python manager.py
```

### 📝 Example Usage

```python
import storagepluss

# Example function call
disk_report = storagepluss.analyze_and_group_files()
print(disk_report)
```

---

## 📂 File Structure

📜 **`manager.py`** - The main script handling file analysis, grouping, and transfer operations.  
📜 **`file_operations.json`** - Log file that records transferred files, their sizes, and timestamps.  
📜 **`requirements.txt`** - Lists the required dependencies for the project.  

---

## 📦 Dependencies

Storagepluss relies on the following Python packages:

- 🛠️ `psutil==7.0.0`
- 📏 `humanize==4.9.0`
- ⏳ `tqdm==4.66.2`
- 🖥️ `pywin32>=307`
- 🎨 `rich==13.7.0`
- 🎨 `colorama==0.4.6`

---

## 🤝 Contributing

We welcome contributions! Follow these steps:

1️⃣ **Fork** the repository.  
2️⃣ Create a new branch (`git checkout -b feature-branch`).  
3️⃣ **Commit** your changes (`git commit -am 'Add new feature'`).  
4️⃣ **Push** to the branch (`git push origin feature-branch`).  
5️⃣ Create a new **Pull Request**.  

---

## 📜 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## 📬 Contact

For questions or suggestions, feel free to reach out at 📧 **[cyberslueth@consultant.com]**.  

Happy cleaning! 🚀💾

