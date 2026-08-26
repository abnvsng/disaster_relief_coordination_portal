"""SmsParser - turns 160 characters of feature-phone text into a report.

Grammar:  HELP <habitation code> <members> <need codes> [<water cm>] [<trapped>]
Example:  HELP DBG012 6 WTR,RTN,FDR 90 0

Forgiving about case, extra spaces and Devanagari digits, strict about
everything else: a report the portal cannot read is worse than no report,
because the sender believes help is coming.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from domain.vocab import NeedType

KEYWORDS = {"HELP", "MADAD", "SAHAYATA", "SOS"}
DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")

NEED_ALIASES = {
    "WATER": "WTR", "PANI": "WTR", "WTR": "WTR",
    "RATION": "RTN", "KHANA": "RTN", "FOOD": "RTN", "RTN": "RTN",
    "FODDER": "FDR", "CHARA": "FDR", "FDR": "FDR",
    "MED": "MED", "MEDICINE": "MED", "DAWA": "MED", "DOCTOR": "MED",
    "SHELTER": "SHL", "TARPAULIN": "SHL", "TIRPAL": "SHL", "SHL": "SHL",
    "BLANKET": "CLO", "KAMBAL": "CLO", "CLOTHES": "CLO", "CLO": "CLO",
    "BABY": "BBY", "INFANT": "BBY", "BBY": "BBY",
    "TOILET": "SAN", "HYGIENE": "SAN", "SAN": "SAN",
    "RESCUE": "RSQ", "BACHAO": "RSQ", "TRAPPED": "RSQ", "RSQ": "RSQ",
}

FORMAT_HELP = (
    "Format: HELP <code> <members> <needs> [<water cm>] [<trapped>]. "
    "Example: HELP DBG012 6 WTR,RTN 90 0"
)


class ParseError(Exception):
    pass


@dataclass
class ParsedReport:
    habitation_code: str
    total_members: int
    needs: list[str] = field(default_factory=list)
    water_depth_m: float = 0.0
    people_trapped: int = 0
    raw: str = ""


class SmsParser:
    def parse_sms(self, text: str) -> ParsedReport:
        if not text or not text.strip():
            raise ParseError(FORMAT_HELP)

        cleaned = text.translate(DEVANAGARI).strip()
        tokens = re.split(r"[\s]+", cleaned.upper())
        if tokens[0] not in KEYWORDS:
            raise ParseError(
                f"Message must start with HELP. {FORMAT_HELP}"
            )
        tokens = tokens[1:]
        if len(tokens) < 3:
            raise ParseError(FORMAT_HELP)

        code = tokens[0]
        if not re.fullmatch(r"[A-Z]{2,4}\d{1,5}", code):
            raise ParseError(
                f"'{code}' is not a habitation code. Codes look like DBG012."
            )

        try:
            members = int(tokens[1])
        except ValueError:
            raise ParseError(f"'{tokens[1]}' is not a number of people. {FORMAT_HELP}")
        if not 1 <= members <= 500:
            raise ParseError("Number of people must be between 1 and 500.")

        needs = self._needs(tokens[2])
        if not needs:
            raise ParseError(
                "No need recognised. Use WTR, RTN, FDR, MED, SHL, CLO, BBY, SAN or RSQ."
            )

        water_cm = self._optional_int(tokens, 3, "water depth")
        trapped = self._optional_int(tokens, 4, "trapped count")

        return ParsedReport(
            habitation_code=code,
            total_members=members,
            needs=needs,
            water_depth_m=round((water_cm or 0) / 100.0, 2),
            people_trapped=trapped or 0,
            raw=text.strip()[:320],
        )

    @staticmethod
    def _needs(token: str) -> list[str]:
        out: list[str] = []
        for part in re.split(r"[,/+;]", token):
            part = part.strip()
            if not part:
                continue
            code = NEED_ALIASES.get(part)
            if code and code not in out:
                out.append(code)
        return out

    @staticmethod
    def _optional_int(tokens: list[str], index: int, label: str) -> int | None:
        if len(tokens) <= index:
            return None
        try:
            return int(tokens[index])
        except ValueError:
            raise ParseError(f"'{tokens[index]}' is not a valid {label}.")


parser = SmsParser()
