"""PR-14b: test del filtro log per la GUI (logica pura)."""

from xtrader_bridge import event_log, log_view


def _entries():
    # Righe formattate come quelle che la GUI tiene in memoria.
    return [
        event_log.format_entry("avvio", "INFO"),
        event_log.format_entry("quota mancante", "WARNING"),
        event_log.format_entry("scrittura fallita", "ERROR"),
        event_log.format_entry("Inter v Milan", "SIGNAL"),
        event_log.format_entry("in ascolto", "INFO"),
    ]


def test_options_sono_tutti_piu_i_livelli_event_log():
    assert log_view.OPTIONS == (log_view.ALL,) + event_log.LEVELS


def test_filtro_tutti_ritorna_tutte_le_righe():
    lines = _entries()
    assert log_view.filter_lines(lines, log_view.ALL) == lines
    # Una nuova lista, non lo stesso oggetto (non muta l'input).
    assert log_view.filter_lines(lines, log_view.ALL) is not lines


def test_filtro_per_livello_noto():
    lines = _entries()
    only_err = log_view.filter_lines(lines, "ERROR")
    # Confronto con la riga GIÀ creata (lines[2]), non con un nuovo format_entry:
    # quest'ultimo userebbe un timestamp now() che, a cavallo del secondo, divergerebbe
    # → test flaky (finding Codex). filter_lines ritorna gli stessi oggetti di `lines`.
    assert only_err == [lines[2]]
    only_info = log_view.filter_lines(lines, "INFO")
    assert len(only_info) == 2
    assert all(event_log.entry_level(l) == "INFO" for l in only_info)


def test_valore_ignoto_o_vuoto_ritorna_tutto():
    lines = _entries()
    assert log_view.filter_lines(lines, "PINCO") == lines
    assert log_view.filter_lines(lines, "") == lines
    assert log_view.filter_lines(lines, None) == lines


def test_matches_predicato_riga_per_riga():
    info = event_log.format_entry("avvio", "INFO")
    err = event_log.format_entry("boom", "ERROR")
    # ALL / ignoto / vuoto → sempre True.
    for sel in (log_view.ALL, "PINCO", "", None):
        assert log_view.matches(info, sel) is True
    # Livello noto → True solo se combacia.
    assert log_view.matches(err, "ERROR") is True
    assert log_view.matches(info, "ERROR") is False
    # filter_lines è coerente con matches.
    lines = [info, err]
    assert log_view.filter_lines(lines, "ERROR") == [l for l in lines if log_view.matches(l, "ERROR")]


def test_filtro_legge_header_non_il_testo():
    # Un "[ERROR]" nel TESTO non deve far passare la riga col filtro ERROR
    # (filter_by_level legge solo il campo header strutturale).
    line = event_log.format_entry("contiene [ERROR] nel testo", "INFO")
    assert log_view.filter_lines([line], "ERROR") == []
    assert log_view.filter_lines([line], "INFO") == [line]
