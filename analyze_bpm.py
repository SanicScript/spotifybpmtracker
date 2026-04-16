import sys
import os
import csv
import librosa

AUDIO_EXTENSIONS = {'.mp3', '.ogg', '.flac', '.wav', '.m4a', '.opus'}

def detect_bpm(file_path):
    """Detect BPM of an audio file using librosa."""
    y, sr = librosa.load(file_path, sr=None)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return round(float(tempo))

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_bpm.py <folder_with_audio_files>")
        sys.exit(1)

    folder = sys.argv[1]
    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a directory.")
        sys.exit(1)

    # Find audio files
    audio_files = []
    for root, dirs, files in os.walk(folder):
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                audio_files.append(os.path.join(root, f))

    if not audio_files:
        print(f"No audio files found in '{folder}'.")
        sys.exit(1)

    print(f"Found {len(audio_files)} audio files. Analyzing BPM...\n")

    results = []
    for i, path in enumerate(audio_files, 1):
        filename = os.path.basename(path)
        name_no_ext = os.path.splitext(filename)[0]
        print(f"  [{i}/{len(audio_files)}] {filename}...", end=" ", flush=True)
        try:
            bpm = detect_bpm(path)
            print(f"{bpm} BPM")
            results.append({'file': filename, 'name': name_no_ext, 'bpm': bpm})
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({'file': filename, 'name': name_no_ext, 'bpm': None})

    # Sort by BPM
    results.sort(key=lambda x: x['bpm'] or 0)

    # Print table
    print(f"\n{'BPM':<6} {'Song'}")
    print("-" * 70)
    for r in results:
        bpm_str = str(r['bpm']) if r['bpm'] else '?'
        print(f"{bpm_str:<6} {r['name']}")

    # Export CSV
    csv_path = os.path.join(folder, "bpm_results.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Filename', 'BPM'])
        for r in results:
            writer.writerow([r['file'], r['bpm']])
    print(f"\nSaved BPM results to: {csv_path}")

if __name__ == '__main__':
    main()
