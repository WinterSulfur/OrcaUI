# orca_parser.py
import re
import json
from pathlib import Path
from typing import Callable, List, Tuple

def write_to_parsed(label: str, value: str, out_path: Path):
    """Записывает найденное значение в parsed.txt рядом с .out"""
    parsed_file = out_path.parent / "parsed.txt"
    with open(parsed_file, 'a', encoding='utf-8') as f:
        f.write(f"{label}: {value}\n")

class OrcaParser:
    def __init__(self):
        self.rules: List[Tuple[re.Pattern, str]] = []
        # Регистрируем правила: (паттерн, метка)
        self.add_rule(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", "Energy")
        self.add_rule(r"Non-thermal \(ZPE\) correction\s+(-?\d+\.\d+)", "ZPE")

    def add_rule(self, pattern: str, label: str):
        self.rules.append((re.compile(pattern), label))

    def parse(self, out_path: Path, project_root: Path):
        if not out_path.is_file():
            return

        # Имя вычисления = имя папки, содержащей Results/
        calculation_name = out_path.parent.parent.name

        parse_file = project_root / "parse.json"
        data = {}
        if parse_file.is_file():
            try:
                with open(parse_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                pass  # Игнорируем повреждённый JSON

        if calculation_name not in data:
            data[calculation_name] = {}

        # Парсинг
        with open(out_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                for regex, label in self.rules:
                    match = regex.search(line)
                    if match:
                        value = float(match.group(1))
                        data[calculation_name][label] = value

        # Сохраняем ВЕСЬ файл заново (атомарно для одного расчёта)
        with open(parse_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)