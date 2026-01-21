# orca_job.py
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal
import subprocess


class OrcaJob(QObject):
    started = Signal(str)          # ← должен быть!
    finished = Signal(str, bool, str)
    error_occurred = Signal(str, str)
    completed = Signal()

    def __init__(self, orca_exe: Path, inp_path: Path, out_path: Path):
        super().__init__()
        self.orca_exe = orca_exe
        self.inp_path = inp_path
        self.out_path = out_path
        self._thread = None
        self._proc = None

    def run(self):
        try:
            inp_name = self.inp_path.name
            self.started.emit(inp_name)  # ← вызывается здесь

            if not self.orca_exe.is_file():
                raise FileNotFoundError(f"ORCA not found: {self.orca_exe}")
            if not self.inp_path.is_file():
                raise FileNotFoundError(f"Input not found: {self.inp_path}")

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

            self._save_output(output)

            success = (returncode == 0) and ("ORCA TERMINATED NORMALLY" in output)
            self.finished.emit(inp_name, success, str(self.out_path))

        except Exception as e:
            err_msg = str(e)
            self.error_occurred.emit(self.inp_path.name, err_msg)
            try:
                self._save_output(f"[FAILED]\n{err_msg}\n")
            except:
                pass
        finally:
            self.completed.emit()

    def _save_output(self, output: str):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, 'w', encoding='utf-8') as f:
            f.write(output)

    def terminate(self):
        if not self._proc:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                output, _ = self._proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                output, _ = self._proc.communicate()
        else:
            output, _ = self._proc.communicate()

        output = output or "[Terminated by user]\n"
        self._save_output(output)

        # ВАЖНО: эмитируем ошибку, чтобы очередь продолжила работу
        self.error_occurred.emit(self.inp_path.name, "Terminated by user")
        self.completed.emit()
        self._proc = None

    def start_async(self):
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self._thread.finished.connect(self._thread.deleteLater)
        self.completed.connect(self._thread.quit)
        self._thread.start()

    def _save_output(self, output):
        if output is None:
            output = ""
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, 'w', encoding='utf-8') as f:
            f.write(str(output))