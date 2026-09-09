import sqlite3

conn = sqlite3.connect("waveload_library.db")
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table'")
for row in cursor:
    print(row[0])
    print()

# Check for duplicates
print("--- Duplicate file_path check ---")
cursor2 = conn.execute("SELECT file_path, COUNT(*) as cnt FROM track_assets GROUP BY file_path HAVING cnt > 1")
dups = cursor2.fetchall()
if dups:
    print(f"Found {len(dups)} duplicate file paths:")
    for d in dups:
        print(f"  {d[0]} => {d[1]} occurrences")
else:
    print("No duplicate file paths found.")

print()
print("--- Track count ---")
print(f"Total tracks: {conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]}")
print(f"Total assets: {conn.execute('SELECT COUNT(*) FROM track_assets').fetchone()[0]}")

conn.close()
