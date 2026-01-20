# orca_queue.py
from pathlib import Path
from PySide6.QtCore import QObject, Signal
import orca_job


class OrcaQueue(QObject):
    job_started = Signal(str)
    job_finished = Signal(str, bool, str)
    queue_finished = Signal()
    error_occurred = Signal(str, str)

    def __init__(self, orca_exe: Path):
        super().__init__()
        self.orca_exe = orca_exe
        self._jobs = []
        self._current_index = -1
        self._active_jobs = []  # ← храним ссылки на активные задачи

    def add_job(self, inp_path: Path, out_path: Path):
        if self._current_index >= 0:
            raise RuntimeError("Cannot add job after queue started")
        self._jobs.append({
            'inp': Path(inp_path),
            'out': Path(out_path),
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

    def start(self):
        if not self._jobs:
            self.queue_finished.emit()
            return
        self._current_index = 0
        self._active_jobs.clear()
        self._run_next_job()

    def _run_next_job(self):
        if self._current_index >= len(self._jobs):
            self._current_index = -1
            self.queue_finished.emit()
            return

        job_info = self._jobs[self._current_index]
        job = orca_job.OrcaJob(
            self.orca_exe,
            job_info['inp'],
            job_info['out']
        )

        # Сохраняем ссылку
        self._active_jobs.append(job)

        # Подключаем все сигналы
        job.started.connect(self.job_started)
        job.finished.connect(self._on_job_finished)
        job.error_occurred.connect(self._on_job_error)
        job.completed.connect(lambda: self._cleanup_job(job))  # ← удаляем из списка

        job.start_async()

    def _cleanup_job(self, job):
        if job in self._active_jobs:
            self._active_jobs.remove(job)

    def _on_job_finished(self, inp_name: str, success: bool, out_path: str):
        self.job_finished.emit(inp_name, success, out_path)
        # Удаляем завершённую задачу из активных
        self._active_jobs[:] = [j for j in self._active_jobs if not hasattr(j, '_finished')]
        # Но лучше — просто очищать после перехода
        self._current_index += 1
        self._run_next_job()

    def _on_job_error(self, inp_name: str, error: str):
        self.error_occurred.emit(inp_name, error)
        self._current_index += 1
        self._run_next_job()