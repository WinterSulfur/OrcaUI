import os
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal
import subprocess


class OrcaJob(QObject):
    started = Signal(str)
    finished = Signal(str, bool, str)
    error_occurred = Signal(str, str)
    completed = Signal()

    def __init__(self, orca_exe: Path, inp_path: Path, out_path: Path, locale: str = "C.UTF-8", disable_gpu: bool = True):
        super().__init__()
        
        # Проверка на None
        if orca_exe is None or str(orca_exe) == "None":
            raise ValueError("orca_exe is None!")
        if inp_path is None or str(inp_path) == "None":
            raise ValueError("inp_path is None!")
        if out_path is None or str(out_path) == "None":
            raise ValueError("out_path is None!")
        self.orca_exe = orca_exe
        self.inp_path = inp_path
        self.out_path = out_path
        self._proc = None
        self._temp_bat = None
        self.orca_locale = locale
        self.disable_gpu = disable_gpu

    def run(self):
        try:
            inp_name = self.inp_path.name
            self.started.emit(inp_name)

            if not self.orca_exe.is_file():
                raise FileNotFoundError(f"ORCA not found: {self.orca_exe}")
            if not self.inp_path.is_file():
                raise FileNotFoundError(f"Input not found: {self.inp_path}")

            calc_dir = str(self.inp_path.parent)
            self.out_path.parent.mkdir(parents=True, exist_ok=True)

            # === Чистое окружение (опционально) ===
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            env.pop('PYTHONHOME', None)
            env['LC_ALL'] = self.orca_locale
            if self.disable_gpu:
                env['CUDA_VISIBLE_DEVICES'] = '-1'
                env['OMPI_MCA_btl'] = 'tcp,self'
                env['OMPI_MCA_pml'] = 'ob1'
                env['UCX_TLS'] = 'tcp'
                env['OMPI_MCA_cuda_support'] = '0'

            # === Запускаем ORCA напрямую (без mpiexec!) ===
            cmd = [str(self.orca_exe), inp_name]

            # Запускаем .bat
            self._proc = subprocess.Popen(
                cmd,
                cwd=calc_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=env,
                close_fds=True,
                start_new_session=True
            )

            # === Потоковая запись вывода ===
            with open(self.out_path, 'w', encoding='utf-8') as f_out:
                while True:
                    line = self._proc.stdout.readline()
                    if not line and self._proc.poll() is not None:
                        break
                    if line:
                        f_out.write(line)
                        f_out.flush()

            returncode = self._proc.wait()

            # Анализируем результат
            success = False
            output = ""
            if self.out_path.is_file():
                with open(self.out_path, 'r', encoding='utf-8', errors='replace') as f:
                    output = f.read()
                success = (returncode == 0) and ("ORCA TERMINATED NORMALLY" in output)

            self.finished.emit(inp_name, success, str(self.out_path))

        except Exception as e:
            err_msg = str(e)
            self.error_occurred.emit(self.inp_path.name, err_msg)
            self._save_output(f"[FAILED]\n{err_msg}\n")
        finally:
            self._cleanup()
            self.completed.emit()

    def _save_output(self, output: str):
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, 'w', encoding='utf-8') as f:
            f.write(output)

    def _cleanup(self):
        """Удаляет временные файлы."""
        if self._temp_bat and self._temp_bat.is_file():
            try:
                self._temp_bat.unlink()
            except:
                pass

    def terminate(self):
        if self._proc and self._proc.poll() is None:
            # Убиваем всю группу процессов по PGID
            try:
                import os
                os.killpg(os.getpgid(self._proc.pid), 15)  # SIGTERM
                self._proc.wait(timeout=5)
            except (ProcessLookupError, TimeoutError, OSError):
                try:
                    os.killpg(os.getpgid(self._proc.pid), 9)  # SIGKILL
                    self._proc.wait(timeout=2)
                except:
                    pass
            except Exception:
                # fallback на обычный terminate/kill
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
        self._cleanup()
        self.completed.emit()

    def start_async(self):
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self._thread.finished.connect(self._thread.deleteLater)
        self.completed.connect(self._thread.quit)
        self._thread.start()