class ErroNegocio(Exception):
    """Violação de regra de negócio (convertida em HTTP pelo handler em main.py)."""

    def __init__(self, mensagem: str, status: int = 400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status


class Duplicada(Exception):
    """Demanda de origem já existente (idempotência da integração)."""

    def __init__(self, tarefa):
        super().__init__("duplicada")
        self.tarefa = tarefa
