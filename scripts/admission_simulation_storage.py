"""Private in-memory SQLite for single-threaded simulations, never deployment.

Retains production SQL and transaction boundaries. The lifetime is one cell.
Do not use this context concurrently within a process or for persistence tests.
"""
from contextlib import contextmanager
import sqlite3

from research.ticket_admission import TicketAdmission


@contextmanager
def memory_sqlite():
    connections = {}
    original = TicketAdmission.db

    @contextmanager
    def db(instance):
        identity = id(instance)
        if identity not in connections:
            conn = sqlite3.connect(':memory:', isolation_level=None)
            conn.row_factory = sqlite3.Row
            connections[identity] = conn
        conn = connections[identity]
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    TicketAdmission.db = db
    try:
        yield
    finally:
        TicketAdmission.db = original
        for conn in connections.values():
            conn.close()
