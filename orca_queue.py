# orca_queue.py
import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal
import orca_job
from orca_parser import OrcaParser

class OrcaQueue(QObject):
    job_started = Signal(str)
    job_finished = Signal(str, bool, str, str)  # inp_name, success, out_path, display_name
    error_occurred = Signal(str, str, str)      # inp_name, error, display_name
    queue_finished = Signal()

    def __init__(self, orca_exe: Path, locale: str = "C.UTF-8", log_dir: Path = None, disable_gpu: bool = True):
        super().__init__()
        self.orca_exe = orca_exe
        self.orca_locale = locale
        self._jobs = []
        self._is_running = False
        self._current_index = 0
        self._active_jobs = []
        self._log_dir = log_dir or Path(__file__).parent.parent / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._log_file = None
        self._stopped = False
        self.disable_gpu = disable_gpu
        self._job_was_terminated = False
        self._parser = OrcaParser()

    def add_job(self, inp_path: Path, out_path: Path):
        if self._is_running:
            raise RuntimeError("Cannot add job while queue is running")
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
        if self._is_running:
            raise RuntimeError("Cannot modify queue while running")
        if 0 <= index < len(self._jobs):
            del self._jobs[index]

    def clear(self):
        """Очистка возможна ВСЕГДА, кроме активного выполнения"""
        if self._is_running:
            raise RuntimeError("Cannot clear while queue is running")
        self._jobs.clear()
        self._current_index = 0  # сброс индекса при очистке

    def is_empty(self) -> bool:
        return len(self._jobs) == 0

    def _write_log(self):
        if not self._log_file:
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{now}] Queue state:\n")
            for i, job in enumerate(self._jobs):
                marker = "→" if i == self._current_index and self._is_running else " "
                f.write(f"{marker}{job['display_name']} → {job['status']}\n")
            f.write("\n")

    def start(self):
        """Полный перезапуск очереди с начала"""
        if self._is_running:
            return
        
        if not self._jobs:
            self.queue_finished.emit()
            return
            
        self._stopped = False
        self._current_index = 0
        self._is_running = True
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_file = self._log_dir / f"{timestamp}.log"
        
        for job in self._jobs:
            job['status'] = '⏹️ Pending'
            
        self._write_log()
        self._active_jobs.clear()
        self._run_next_job()

    def resume(self):
        """Продолжение с текущего индекса (включая пересчёт прерванного)"""
        if self._is_running:
            return
            
        if not self._jobs:
            self.queue_finished.emit()
            return
            
        if self._current_index >= len(self._jobs):
            self.queue_finished.emit()
            return
            
        self._stopped = False
        self._job_was_terminated = False 
        self._is_running = True
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._log_file = self._log_dir / f"{timestamp}_resume.log"
        
        for i in range(self._current_index, len(self._jobs)):
            self._jobs[i]['status'] = '⏹️ Pending'
            
        self._write_log()
        self._active_jobs.clear()
        self._run_next_job()

    def _run_next_job(self):
        if self._stopped or self._current_index >= len(self._jobs):
            self._finalize_queue()
            return

        job_info = self._jobs[self._current_index]
        job_info['status'] = '▶️ Running'
        self._write_log()

        job = orca_job.OrcaJob(
            self.orca_exe,
            job_info['inp'],
            job_info['out'],
            locale=self.orca_locale,
            disable_gpu=self.disable_gpu
        )

        self._active_jobs.append(job)

        job.started.connect(self.job_started)
        job.finished.connect(self._on_job_finished)
        job.error_occurred.connect(self._on_job_error)
        job.completed.connect(lambda: self._cleanup_job(job))

        job.start_async()

    def _finalize_queue(self):
        """Централизованный сброс состояния при завершении"""
        self._is_running = False
        self._log_file = None
        self.queue_finished.emit()

    def _cleanup_job(self, job):
        if job in self._active_jobs:
            self._active_jobs.remove(job)

    def _on_job_finished(self, inp_name: str, success: bool, out_path: str):
        try:
            if 0 <= self._current_index < len(self._jobs):
                status = '✅ Success' if success else '❌ Failed'
                job = self._jobs[self._current_index]
                job['status'] = status
                display_name = job['display_name']
                self._write_log()
                if success:
                    out_path_obj = Path(out_path)
                    project_root = out_path_obj.parent.parent.parent
                    self._parser.parse(out_path_obj, project_root)
                self.job_finished.emit(inp_name, success, out_path, display_name)
        finally:
            # ← Условное увеличение индекса
            if not self._job_was_terminated:
                self._current_index += 1
            else:
                self._job_was_terminated = False  # сброс флага

            if self._current_index >= len(self._jobs) or self._stopped:
                self._finalize_queue()
            else:
                self._run_next_job()

    def _on_job_error(self, inp_name: str, error: str):
        try:
            if 0 <= self._current_index < len(self._jobs):
                job = self._jobs[self._current_index]
                job['status'] = '⚠️ Error'
                display_name = job['display_name']
                self._write_log()
                self.error_occurred.emit(inp_name, error, display_name)
        finally:
            if not self._job_was_terminated:
                self._current_index += 1
            else:
                self._job_was_terminated = False

            if self._current_index >= len(self._jobs) or self._stopped:
                self._finalize_queue()
            else:
                self._run_next_job()

    def terminate_current_job(self):
        if not self._is_running:
            return
        self._stopped = True
        self._job_was_terminated = True  
        if self._active_jobs:
            job = self._active_jobs[0]
            job.terminate()

    def get_display_name(self, index: int) -> str:
        if 0 <= index < len(self._jobs):
            return self._jobs[index]['display_name']
        return ""
    
    def get_job_data(self, index: int):
        if 0 <= index < len(self._jobs):
            job = self._jobs[index]
            return {
                'inp': job['inp'],
                'out': job['out'],
                'display_name': job['display_name']
            }
        return None