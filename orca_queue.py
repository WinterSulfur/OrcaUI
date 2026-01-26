# orca_queue.py
import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal
import orca_job


class OrcaQueue(QObject):
    job_started = Signal(str)
    job_finished = Signal(str, bool, str, str)  # inp_name, success, out_path, display_name
    error_occurred = Signal(str, str, str)      # inp_name, error, display_name
    queue_finished = Signal()

    def __init__(self, orca_exe: Path, locale: str = "C.UTF-8", log_dir: Path = None):
        super().__init__()
        self.orca_exe = orca_exe
        self._jobs = []
        self._current_index = -1
        self._active_jobs = []
        self._log_dir = log_dir or Path(__file__).parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._log_file = None
        self.orca_locale = locale
        self._stopped = False

    def add_job(self, inp_path: Path, out_path: Path):
        if self._current_index >= 0:
            raise RuntimeError("Cannot add job after queue started")
        try:
            parent2 = inp_path.parent.parent.name
            if not parent2:
                parent2 = inp_path.parent.name
        except Exception:
            parent2 = "root"
        display_name = f"{parent2} : {inp_path.name}"
        self._jobs.append({
            'inp': inp_path,
            'out': out_path,
            'display_name': display_name,
            'status': '⏹️ Pending'
        })

    def remove_job(self, index: int):
        if self._current_index >= 0:
            raise RuntimeError("Cannot remove job after queue started")
        if 0 <= index < len(self._jobs):
            del self._jobs[index]

    def clear(self):
        if self._current_index >= 0:
            raise RuntimeError("Cannot clear after queue started")
        self._jobs.clear()

    def is_empty(self) -> bool:
        return len(self._jobs) == 0

    def _write_log(self):
        if not self._log_file:
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{now}] Queue state:\n")
            for job in self._jobs:
                f.write(f"{job['display_name']} → {job['status']}\n")
            f.write("\n")

    def start(self):
        if not self._jobs:
            self.queue_finished.emit()
            return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_file = self._log_dir / f"{timestamp}.log"
        for job in self._jobs:
            job['status'] = '⏹️ Pending'
        self._write_log()
        self._current_index = 0
        self._active_jobs.clear()
        self._run_next_job()

    def _run_next_job(self):
        if self._stopped or self._current_index >= len(self._jobs):
            self._current_index = -1
            self._log_file = None
            self.queue_finished.emit()
            return

        job_info = self._jobs[self._current_index]
        job_info['status'] = '▶️ Running'
        self._write_log()

        job = orca_job.OrcaJob(
            self.orca_exe,
            job_info['inp'],
            job_info['out'],
            locale=self.orca_locale
        )

        self._active_jobs.append(job)

        # Передаём сигналы дальше
        job.started.connect(self.job_started)
        job.finished.connect(self._on_job_finished)
        job.error_occurred.connect(self._on_job_error)
        job.completed.connect(lambda: self._cleanup_job(job))

        job.start_async()

    def _cleanup_job(self, job):
        if job in self._active_jobs:
            self._active_jobs.remove(job)

    def _on_job_finished(self, inp_name: str, success: bool, out_path: str):
        if 0 <= self._current_index < len(self._jobs):
            status = '✅ Success' if success else '❌ Failed'
            job = self._jobs[self._current_index]
            job['status'] = status
            display_name = job['display_name']  # ← сохраняем здесь
            self._write_log()
            # Эмитим сигнал с display_name
            self.job_finished.emit(inp_name, success, out_path, display_name)
        self._current_index += 1
        self._run_next_job()

    def _on_job_error(self, inp_name: str, error: str):
        if 0 <= self._current_index < len(self._jobs):
            job = self._jobs[self._current_index]
            job['status'] = '⚠️ Error'
            display_name = job['display_name']
            self._write_log()
            self.error_occurred.emit(inp_name, error, display_name)
        self._current_index += 1
        self._run_next_job()

    def terminate_current_job(self):
        self._stopped = True  # ← помечаем, что очередь остановлена
        if self._active_jobs:
            job = self._active_jobs[0]
            job.terminate()

    def get_display_name(self, index: int) -> str:
        if 0 <= index < len(self._jobs):
            return self._jobs[index]['display_name']
        return ""