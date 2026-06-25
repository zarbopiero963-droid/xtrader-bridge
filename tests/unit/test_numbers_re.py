"""Test del frammento regex decimale condiviso (audit L4): `numbers_re` è la fonte unica
usata da parser/validator/custom_pipeline/csv_writer. Qui si verifica che i frammenti
matchino i casi attesi e che i consumer continuino a usarli (anti-drift)."""

import re

from xtrader_bridge import csv_writer, custom_pipeline, numbers_re, parser, validator


def test_decimal_match_atteso():
    rx = re.compile(r"^" + numbers_re.DECIMAL + r"$")
    assert rx.fullmatch("1")
    assert rx.fullmatch("1.85")
    assert rx.fullmatch("0,5")
    assert not rx.fullmatch("1.2.3")     # niente doppio separatore
    assert not rx.fullmatch("-1")        # DECIMAL è senza segno
    assert not rx.fullmatch("1e2")       # niente esponenti


def test_signed_decimal_accetta_il_segno():
    rx = re.compile(r"^" + numbers_re.SIGNED_DECIMAL + r"$")
    assert rx.fullmatch("-1")
    assert rx.fullmatch("+1,5")
    assert rx.fullmatch("1.85")
    assert not rx.fullmatch("--1")


def test_consumer_usano_il_frammento_condiviso():
    # I quattro moduli compongono il frammento unico (fonte unica, anti-drift): se uno
    # divergesse, questi pattern non corrisponderebbero più al frammento.
    assert numbers_re.DECIMAL in parser._NUM
    assert numbers_re.DECIMAL in validator._DECIMAL_PRICE.pattern
    assert numbers_re.SIGNED_DECIMAL in custom_pipeline._HANDICAP_RE.pattern
    assert numbers_re.SIGNED_DECIMAL in csv_writer._NUMERIC_RE.pattern
