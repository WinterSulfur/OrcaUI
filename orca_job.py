# orca_job.py
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal
import subprocess


class OrcaJob(QObject):
    # ... существующие сигналы ...
    def __init__(self, orca_exe: Path, inp_path: Path, out_path: Path):
        super().__init__()
        self.orca_exe = orca_exe
        self.inp_path = inp_path
        self.out_path = out_path
        self._thread = None
        self._proc = None  # ← для хранения subprocess

    def run(self):
        try:
            # ... проверки ...
            calc_dir = self.inp_path.parent
            self._proc = subprocess.Popen(
                [str(self.orca_exe), self.inp_path.name],
                cwd=calc_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            output, _ = self._proc.communicate()
            returncode = self._proc.returncode
            self._proc = None

            # Сохраняем вывод
            self._save_output(output)

            success = (returncode == 0) and ("ORCA TERMINATED NORMALLY" in output)
            self.finished.emit(self.inp_path.name, success, str(self.out_path))

        except Exception as e:
            pass
        finally:
            self.completed.emit()

    def _save_output(self, output: str):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, 'w', encoding='utf-8') as f:
            f.write(output)

    def terminate(self):
        """Принудительно завершить ORCA и сохранить текущий вывод."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                output, _ = self._proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                output, _ = self._proc.communicate()
            self._save_output(output)