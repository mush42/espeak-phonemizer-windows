# coding: utf-8


import os
import sys
import re
import struct
import subprocess
import typing
from pathlib import Path

_DIR = Path(__file__).parent
__version__ = (_DIR / "VERSION").read_text().strip()
TEMPFILENAME = "espk_ph"
ARCH = "x86" if struct.calcsize("P") == 4 else "x64"
ESPEAK_NG_DIR = _DIR / "espeakng"
ESPEAK_DATA_PATH = ESPEAK_NG_DIR
ESPEAK_NG_EXE = ESPEAK_NG_DIR / ARCH / "espeak-ng.exe"
ZWNJ = bytes(chr(0x200C), "utf-8")


class Phonemizer:
    """
    Use espeak-ng executable to get IPA phonemes from text.
    """

    LANG_SWITCH_FLAG = re.compile(r"\([^)]*\)")
    STRESS_PATTERN = re.compile(r"[ˈˌ]")
    DEFAULT_CLAUSE_BREAKERS = {",", ";", ":", ".", "!", "?"}

    def __init__(
        self,
        default_voice: typing.Optional[str] = None,
        clause_breakers: typing.Optional[typing.Collection[str]] = None,
    ):
        self.current_voice: typing.Optional[str] = None
        self.default_voice = default_voice
        self.clause_breakers = clause_breakers or Phonemizer.DEFAULT_CLAUSE_BREAKERS

    def phonemize(
        self,
        text: str,
        voice: typing.Optional[str] = None,
        keep_clause_breakers: bool = False,
        phoneme_separator: typing.Optional[str] = None,
        word_separator: str = " ",
        punctuation_separator: str = "",
        keep_language_flags: bool = False,
        no_stress: bool = False,
    ) -> str:
        """
        Return IPA string for text.

        Args:
            text: Text to phonemize
            voice: optional voice (uses self.default_voice if None)
            keep_clause_breakers: True if punctuation symbols should be kept
            phoneme_separator: Separator character between phonemes
            word_separator: Separator string between words (default: space)
            punctuation_separator: Separator string between before punctuation (keep_clause_breakers=True)
            keep_language_flags: True if language switching flags should be kept
            no_stress: True if stress characters should be removed

        Returns:
            ipa - string of IPA phonemes
        """
        cmd_args = [
            "-q",
            "--stdin",
            "--ipa",
            "-b=1",
            '--sep="z"',
            f'--path="{os.fspath(ESPEAK_DATA_PATH)}"',
        ]

        voice = voice or self.default_voice
        if (voice is not None) and (voice != self.current_voice):
            self.current_voice = voice
        cmd_args.append(f'-v "{self.current_voice}"')

        text += " "
        missing_breakers = []
        if keep_clause_breakers and self.clause_breakers:
            missing_breakers = [c for c in text if c in self.clause_breakers]
        ph_output = self._call_espeakng(cmd_args, {"input": text.encode("utf-8")})
        if phoneme_separator:
            ph_output = ph_output.replace(ZWNJ, bytes(phoneme_separator, "utf-8"))
        else:
            ph_output = ph_output.replace(ZWNJ, b"")
        phoneme_lines = ph_output.decode("utf-8").splitlines()

        if not keep_language_flags:
            # Remove language switching flags, e.g. (en)
            phoneme_lines = [
                Phonemizer.LANG_SWITCH_FLAG.sub("", line) for line in phoneme_lines
            ]

        if word_separator != " ":
            # Split/re-join words
            for line_idx in range(len(phoneme_lines)):
                phoneme_lines[line_idx] = word_separator.join(
                    phoneme_lines[line_idx].split()
                )
        # Re-insert clause breakers
        if missing_breakers:
            # pylint: disable=consider-using-enumerate
            for line_idx in range(len(phoneme_lines)):
                if line_idx < len(missing_breakers):
                    phoneme_lines[line_idx] += (
                        punctuation_separator + missing_breakers[line_idx]
                    )
        phonemes_str = word_separator.join(line.strip() for line in phoneme_lines)
        if no_stress:
            # Remove primary/secondary stress markers
            phonemes_str = Phonemizer.STRESS_PATTERN.sub("", phonemes_str)
        # Clean up multiple phoneme separators
        if phoneme_separator:
            phonemes_str = re.sub(
                "[" + re.escape(phoneme_separator) + "]+",
                phoneme_separator,
                phonemes_str,
            )
        return phonemes_str

    @staticmethod
    def _call_espeakng(args, popen_kwargs=None):
        popen_kwargs = popen_kwargs or {}
        args = [os.fspath(ESPEAK_NG_EXE), *args]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        ret = subprocess.run(
            " ".join(args),
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo,
            **popen_kwargs,
        )
        ret.check_returncode()
        return ret.stdout
