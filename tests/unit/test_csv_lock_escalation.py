"""Test di `xtrader_bridge.csv_lock_escalation` — escalation su CSV-lock (#153 H2).

Pura, headless: esercita il contatore con soglia e le transizioni escalation/recovery.
"""

import threading

from xtrader_bridge.csv_lock_escalation import DEFAULT_THRESHOLD, CsvLockEscalation


def test_soglia_default_e_valori_invalidi_failsafe():
    assert CsvLockEscalation().threshold == DEFAULT_THRESHOLD
    assert CsvLockEscalation(threshold=1).threshold == 1
    assert CsvLockEscalation(threshold=5).threshold == 5
    # bool / non numerico / < 1 → default
    assert CsvLockEscalation(threshold=True).threshold == DEFAULT_THRESHOLD
    assert CsvLockEscalation(threshold="x").threshold == DEFAULT_THRESHOLD
    assert CsvLockEscalation(threshold=0).threshold == DEFAULT_THRESHOLD
    assert CsvLockEscalation(threshold=-3).threshold == DEFAULT_THRESHOLD


def test_escalation_scatta_una_sola_volta_alla_soglia():
    esc = CsvLockEscalation(threshold=3)
    assert esc.record_failure() is False   # 1
    assert esc.count == 1
    assert esc.record_failure() is False   # 2
    assert esc.record_failure() is True    # 3 → entra in escalation (una volta sola)
    assert esc.escalated is True
    assert esc.record_failure() is False   # 4 → già escalato, non riscatta
    assert esc.count == 4


def test_success_azzera_e_segnala_recovery_una_volta():
    esc = CsvLockEscalation(threshold=2)
    esc.record_failure()
    assert esc.record_failure() is True    # escalato
    assert esc.record_success() is True    # era escalato → recovery
    assert esc.count == 0
    assert esc.escalated is False
    # un secondo success senza nuovi fallimenti non è un recovery
    assert esc.record_success() is False


def test_dopo_recovery_serve_di_nuovo_la_soglia():
    esc = CsvLockEscalation(threshold=2)
    esc.record_failure()
    esc.record_failure()                   # escalato
    esc.record_success()                   # reset
    assert esc.record_failure() is False   # 1 dopo reset: non riscatta subito
    assert esc.record_failure() is True    # 2 → riscatta


def test_messaggi_escalation_e_recovery():
    esc = CsvLockEscalation(threshold=1)
    esc.record_failure()
    txt = esc.text(path="C:/x/signals.csv")
    assert "BLOCCATO" in txt and "1" in txt and "signals.csv" in txt
    assert "sblocc" in CsvLockEscalation.recovery_text().lower()


def test_thread_safety_conteggio_atomico():
    # Molti thread che registrano fallimenti: il conteggio finale è esatto (no race).
    esc = CsvLockEscalation(threshold=10_000)

    def worker():
        for _ in range(1000):
            esc.record_failure()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert esc.count == 8 * 1000
