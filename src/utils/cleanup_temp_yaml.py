import os
import tempfile

def cleanup_yaml_temp_files():
    temp_dir = tempfile.gettempdir()
    deleted_files = []

    for filename in os.listdir(temp_dir):
        if filename.startswith("tmp") and filename.endswith(".yaml"):
            file_path = os.path.join(temp_dir, filename)
            try:
                os.remove(file_path)
                deleted_files.append(filename)
            except Exception as e:
                print(f"⚠️ Impossibile eliminare {filename}: {e}")

    if deleted_files:
        print(f"✅ Rimossi {len(deleted_files)} file YAML temporanei:")
        for f in deleted_files:
            print(f"  - {f}")
    else:
        print("ℹ️ Nessun file YAML temporaneo da eliminare.")

if __name__ == "__main__":
    cleanup_yaml_temp_files()
