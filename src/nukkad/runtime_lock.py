import os


class RuntimeLock:
    """Hold an OS lock while one application owns a personal data directory."""

    def __init__(self, root):
        self.path = root / "application.lock"
        self.file = None

    def acquire(self):
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                self.file.write(b"0")
                self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise ValueError(
                "Nukkad is already running for this data directory; use the existing app or stop it first"
            ) from None

    def release(self):
        if self.file:
            self.file.close()
            self.file = None
