"""Erreurs métier : leur message est montré tel quel à l'utilisateur."""


class UserError(Exception):
    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(UserError):
    status_code = 404


class Conflict(UserError):
    status_code = 409


class FileTooLarge(UserError):
    status_code = 413


class UnsupportedMedia(UserError):
    status_code = 415


class ModelsMissing(UserError):
    status_code = 503


class Cancelled(Exception):
    """Levée par un traitement quand l'utilisateur a demandé l'annulation."""
