import os
import sys
import hashlib
import json
import shutil
import datetime

#------python code-----
# ----------- Utility functions ------------

def repo_path(*paths):
    """Return path inside .myvcs folder"""
    return os.path.join(".myvcs", *paths)

def file_sha1(path):
    """Calculate SHA-1 hash of file content"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def read_json(path):
    with open(path) as f:
        return json.load(f)

def ensure_repo():
    if not os.path.exists(".myvcs"):
        print("Not a myvcs repository (or any of the parent directories). Run 'myvcs.py init' first.")
        sys.exit(1)

# ----------- Core Classes ------------

class Repository:
    def __init__(self):
        ensure_repo()
        self.head_path = repo_path("HEAD")
        self.commits_path = repo_path("commits")
        self.objects_path = repo_path("objects")
        self.index_path = repo_path("index")
        self.branches_path = repo_path("branches")
        self.load_head()

    def load_head(self):
        if os.path.exists(self.head_path):
            with open(self.head_path) as f:
                self.head = f.read().strip()
        else:
            self.head = "master"

    def save_head(self):
        with open(self.head_path, "w") as f:
            f.write(self.head)

    def get_current_commit(self):
        branch_file = os.path.join(self.branches_path, self.head)
        if os.path.exists(branch_file):
            with open(branch_file) as f:
                return f.read().strip()
        return None

    def update_branch(self, commit_hash):
        branch_file = os.path.join(self.branches_path, self.head)
        with open(branch_file, "w") as f:
            f.write(commit_hash)

    def read_index(self):
        if os.path.exists(self.index_path):
            return read_json(self.index_path)
        return {}

    def write_index(self, index):
        write_json(self.index_path, index)

    def add(self, files):
        index = self.read_index()
        for file in files:
            if not os.path.exists(file):
                print(f"Warning: File '{file}' does not exist.")
                continue
            sha = file_sha1(file)
            index[file] = sha
            # Save file content as object
            obj_path = os.path.join(self.objects_path, sha)
            if not os.path.exists(obj_path):
                shutil.copyfile(file, obj_path)
            print(f"Added '{file}'")
        self.write_index(index)

    def commit(self, message):
        index = self.read_index()
        if not index:
            print("Nothing to commit, staging area is empty.")
            return

        # Commit data structure
        commit = {
            "message": message,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "files": index,
            "parent": self.get_current_commit()
        }

        # Serialize commit to json and hash it
        commit_data = json.dumps(commit, sort_keys=True).encode()
        commit_hash = hashlib.sha1(commit_data).hexdigest()

        # Save commit
        commit_path = os.path.join(self.commits_path, commit_hash + ".json")
        with open(commit_path, "wb") as f:
            f.write(commit_data)

        # Update branch pointer and clear staging
        self.update_branch(commit_hash)
        self.write_index({})
        print(f"Committed to {self.head}: {commit_hash[:7]} - {message}")

    def log(self):
        commit_hash = self.get_current_commit()
        if not commit_hash:
            print("No commits yet.")
            return
        while commit_hash:
            commit_path = os.path.join(self.commits_path, commit_hash + ".json")
            if not os.path.exists(commit_path):
                break
            commit = read_json(commit_path)
            print(f"commit {commit_hash}")
            print(f"Date: {commit['timestamp']}")
            print(f"\n    {commit['message']}\n")
            commit_hash = commit.get("parent")

    def status(self):
        index = self.read_index()
        print("Staged files:")
        for f in index:
            print(f"  {f}")
        print()

        # Show changes in working directory vs last commit
        current_commit_hash = self.get_current_commit()
        last_files = {}
        if current_commit_hash:
            commit_path = os.path.join(self.commits_path, current_commit_hash + ".json")
            last_commit = read_json(commit_path)
            last_files = last_commit["files"]

        print("Changes since last commit:")
        changed = False
        for f in os.listdir("."):
            if os.path.isfile(f) and not f.startswith(".myvcs"):
                sha = file_sha1(f)
                last_sha = last_files.get(f)
                if sha != last_sha:
                    print(f"  modified: {f}")
                    changed = True
        if not changed:
            print("  no changes")

    def checkout(self, target):
        # Target can be a commit hash or branch name
        commit_hash = None
        branch_path = os.path.join(self.branches_path, target)
        if os.path.exists(branch_path):
            with open(branch_path) as f:
                commit_hash = f.read().strip()
            self.head = target
            self.save_head()
            print(f"Switched to branch '{target}'")
        else:
            # Try commit hash directly
            commit_path = os.path.join(self.commits_path, target + ".json")
            if os.path.exists(commit_path):
                commit_hash = target
                print(f"Checked out commit {target[:7]} (detached HEAD)")
                self.head = None
                self.save_head()
            else:
                print(f"error: unknown branch or commit '{target}'")
                return

        if not commit_hash:
            print("error: commit not found")
            return

        commit_path = os.path.join(self.commits_path, commit_hash + ".json")
        commit = read_json(commit_path)
        files = commit["files"]

        # Overwrite files with committed versions
        for filename, sha in files.items():
            obj_path = os.path.join(self.objects_path, sha)
            shutil.copyfile(obj_path, filename)
        print(f"Checked out files from commit {commit_hash[:7]}")

    def branch(self, name):
        branch_file = os.path.join(self.branches_path, name)
        if os.path.exists(branch_file):
            print(f"Branch '{name}' already exists.")
            return
        current_commit = self.get_current_commit()
        if not current_commit:
            print("No commits to branch from.")
            return
        with open(branch_file, "w") as f:
            f.write(current_commit)
        print(f"Created branch '{name}' at {current_commit[:7]}")

# ----------- Command line interface ------------

def init():
    if os.path.exists(".myvcs"):
        print("Repository already initialized.")
        return
    os.makedirs(".myvcs")
    os.makedirs(repo_path("commits"))
    os.makedirs(repo_path("objects"))
    os.makedirs(repo_path("branches"))
    # Initialize master branch with no commits
    with open(repo_path("HEAD"), "w") as f:
        f.write("master")
    print("Initialized empty myvcs repository.")

def main():
    if len(sys.argv) < 2:
        print("Usage: myvcs.py <command> [<args>]")
        print("Commands: init, add, commit, log, status, checkout, branch")



return
    cmd = sys.argv[1]

    if cmd == "init":
        init()
        return

    repo = Repository()

    if cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: myvcs.py add <file1> [file2 ...]")
            return
        repo.add(sys.argv[2:])

    elif cmd == "commit":
        if len(sys.argv) < 3:
            print("Usage: myvcs.py commit <message>")
            return
        message = " ".join(sys.argv[2:])
        repo.commit(message)

    elif cmd == "log":
        repo.log()

    elif cmd == "status":
        repo.status()

    elif cmd == "checkout":
        if len(sys.argv) < 3:
            print("Usage: myvcs.py checkout <branch_or_commit>")
            return
        repo.checkout(sys.argv[2])

    elif cmd == "branch":
        if len(sys.argv) < 3:
            print("Usage: myvcs.py branch <branch_name>")
            return
        repo.branch(sys.argv[2])

    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()

