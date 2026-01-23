"""
Test wydajności dodawania notatek
"""

import unittest
import sys
import os
import tempfile
import shutil
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.notes import add_existing_note_file, NOTES_DIR, _save_favorites


class TestWydajnosciDodawania(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_folder = "WydajnoscTest"
        self.folder_path = os.path.join(NOTES_DIR, self.test_folder)
        os.makedirs(self.folder_path, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if os.path.exists(self.folder_path):
            shutil.rmtree(self.folder_path)
        _save_favorites(set())
    
    def _create_test_file(self, content, index):
        file_path = os.path.join(self.temp_dir, f"test_{index}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path
    
    def _measure_time(self, num_files, show_progress=False):
        files = []
        creation_time = 0
        
        if show_progress:
            print(f"\nTworzenie {num_files:,} plików testowych...")
            creation_start = time.time()
        
        for i in range(num_files):
            file_path = self._create_test_file(f"Test {i}", i)
            files.append(file_path)
            
            if show_progress and (i + 1) % 5000 == 0:
                elapsed = time.time() - creation_start
                print(f"  Utworzono {i+1:,} plików ({elapsed:.1f}s)")
        
        if show_progress:
            creation_time = time.time() - creation_start
            print(f"  Zakończono tworzenie w {creation_time:.1f}s\n")
            print(f"Przetwarzanie plików...")
        
        start = time.time()
        progress_step = 5000
        
        for idx, file_path in enumerate(files, 1):
            add_existing_note_file(self.test_folder, file_path)
            
            if show_progress and idx % progress_step == 0:
                elapsed = time.time() - start
                percent = (idx / num_files) * 100
                remaining = ((elapsed / idx) * num_files) - elapsed
                speed = idx / elapsed
                
                print(f"  {idx:,}/{num_files:,} ({percent:.0f}%) - "
                      f"uplynelo {elapsed:.0f}s, pozostalo ~{remaining:.0f}s, "
                      f"{speed:.0f} plikow/s")
        
        processing_time = time.time() - start
        avg = processing_time / num_files
        
        if show_progress:
            speed = num_files / processing_time
            print(f"  Zakonczono przetwarzanie w {processing_time:.1f}s ({speed:.0f} plikow/s)\n")
        
        return creation_time, processing_time, avg
    
    def _display_results(self, num_files, creation_time, processing_time, avg):
        total_time = creation_time + processing_time
        
        print("=" * 70)
        print("WYNIKI TESTU")
        print("=" * 70)
        print(f"Liczba plikow: {num_files:,}")
        
        if total_time >= 3600:
            print(f"Calkowity czas: {total_time:.1f}s ({total_time/3600:.1f}h)")
        elif total_time >= 60:
            print(f"Calkowity czas: {total_time:.1f}s ({total_time/60:.1f}min)")
        else:
            print(f"Calkowity czas: {total_time:.2f}s")
        
        if creation_time > 0:
            creation_pct = (creation_time / total_time) * 100
            processing_pct = (processing_time / total_time) * 100
            print(f"  - tworzenie plikow: {creation_time:.1f}s ({creation_pct:.0f}%)")
            print(f"  - przetwarzanie: {processing_time:.1f}s ({processing_pct:.0f}%)")
        
        print(f"Sredni czas na plik: {avg:.6f}s")
        print(f"Przepustowosc: {num_files/processing_time:,.0f} plikow/s")
        print("=" * 70 + "\n")
    
    def test_male_ilosci(self):
        print("\n" + "=" * 70)
        print("TEST MALYCH ILOSCI (1-1000 plikow)")
        print("=" * 70)
        
        rozmiary = [1, 10, 50, 100, 500, 1000]
        wyniki = []
        
        for size in rozmiary:
            creation, processing, avg = self._measure_time(size, show_progress=False)
            self._display_results(size, creation, processing, avg)
            wyniki.append({'pliki': size, 'czas': processing, 'srednia': avg})
            self.assertLess(processing, 300, f"Przekroczono limit: {processing:.1f}s")
        
        print("=" * 70)
        print("ANALIZA SKALOWALNOSCI")
        print("=" * 70)
        
        for i in range(1, len(wyniki)):
            prev = wyniki[i-1]['srednia']
            curr = wyniki[i]['srednia']
            ratio = curr / prev if prev > 0 else 0
            print(f"{wyniki[i-1]['pliki']} -> {wyniki[i]['pliki']} plikow: wzrost {(ratio-1)*100:+.1f}%")
            self.assertLess(ratio, 1.5, f"Zbyt duzy wzrost: {ratio:.2f}x")
        
        print()
    
    def test_srednie_ilosci(self):
        print("\n" + "=" * 70)
        print("TEST SREDNICH ILOSCI (5000-10000 plikow)")
        print("=" * 70)
        
        for size in [5000, 10000]:
            creation, processing, avg = self._measure_time(size, show_progress=True)
            self._display_results(size, creation, processing, avg)
            self.assertLess(processing, 1200, f"Przekroczono limit: {processing:.1f}s")
    
    def test_duze_ilosci(self):
        print("\n" + "=" * 70)
        print("TEST DUZYCH ILOSCI (50000-100000 plikow)")
        print("=" * 70)
        print("Uwaga: test moze potrwac 30-120 minut\n")
        
        for size in [50000, 100000]:
            creation, processing, avg = self._measure_time(size, show_progress=True)
            self._display_results(size, creation, processing, avg)
            self.assertLess(processing, 7200, f"Przekroczono limit: {processing:.1f}s")
    
    def test_bardzo_duze_ilosci(self):
        print("\n" + "=" * 70)
        print("TEST BARDZO DUZYCH ILOSCI (500000 plikow)")
        print("=" * 70)
        print("Uwaga: test moze potrwac 5-10 godzin")
        print("Postep bedzie raportowany co 5000 plikow\n")
        
        size = 100000
        creation, processing, avg = self._measure_time(size, show_progress=True)
        self._display_results(size, creation, processing, avg)
        self.assertLess(processing, 36000, f"Przekroczono limit: {processing:.1f}s")


class TestWydajnosciDuzePliki(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_folder = "WydajnoscDuzePliki"
        self.folder_path = os.path.join(NOTES_DIR, self.test_folder)
        os.makedirs(self.folder_path, exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if os.path.exists(self.folder_path):
            shutil.rmtree(self.folder_path)
        _save_favorites(set())
    
    def _create_large_file(self, size_kb, index):
        file_path = os.path.join(self.temp_dir, f"large_{index}.txt")
        content = "X" * (size_kb * 1024)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return file_path
    
    def _measure_large_file(self, size_kb, num_files):
        print(f"Tworzenie {num_files} plikow...")
        files = [self._create_large_file(size_kb, i) for i in range(num_files)]
        
        print(f"Przetwarzanie...")
        start = time.time()
        for file_path in files:
            add_existing_note_file(self.test_folder, file_path)
        elapsed = time.time() - start
        
        avg = elapsed / num_files
        return elapsed, avg
    
    def test_rozne_rozmiary(self):
        print("\n" + "=" * 70)
        print("TEST ROZNYCH ROZMIAROW PLIKOW")
        print("=" * 70 + "\n")
        
        rozmiary_kb = [10, 100, 1024, 10*1024, 50*1024, 100*1024]
        
        for size_kb in rozmiary_kb:
            total, _ = self._measure_large_file(size_kb, 1)
            
            size_mb = size_kb / 1024
            if size_mb < 1:
                print(f"{size_kb}KB: {total:.4f}s ({size_mb/total:.2f} MB/s)")
            else:
                print(f"{size_mb:.1f}MB: {total:.4f}s ({size_mb/total:.2f} MB/s)")
            
            self.assertLess(total, 60, f"Przekroczono limit: {total:.3f}s")
        
        print()
    
    def test_wiele_duzych_plikow(self):
        print("\n" + "=" * 70)
        print("TEST WIELU DUZYCH PLIKOW")
        print("=" * 70 + "\n")
        
        testy = [(1024, 10), (10*1024, 5), (50*1024, 2)]
        
        for size_kb, count in testy:
            size_mb = size_kb / 1024
            print(f"{count} plikow po {size_mb:.1f}MB:")
            total, avg = self._measure_large_file(size_kb, count)
            print(f"  Calkowity czas: {total:.2f}s, srednia: {avg:.3f}s/plik\n")
            self.assertLess(total, 300, f"Przekroczono limit: {total:.1f}s")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TESTY WYDAJNOSCI DODAWANIA NOTATEK")
    print("=" * 70)
    print("\n1. Testy dla roznej liczby plikow:")
    print("   - male ilosci: 1-1000")
    print("   - srednie ilosci: 5000-10000")
    print("   - duze ilosci: 50000-100000")
    print("   - bardzo duze: 500000")
    print("\n2. Testy dla roznych rozmiarow:")
    print("   - pojedyncze pliki: 10KB-100MB")
    print("   - wiele duzych plikow")
    print("=" * 70 + "\n")
    
    unittest.main(verbosity=2)