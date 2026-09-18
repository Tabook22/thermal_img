from pathlib import Path
import pytest
from app.thermal import DecodeError, DjiCliDecoder

def test_decoder_rejects_unavailable_sdk():
    decoder = DjiCliDecoder(Path("missing-dji-irp.exe"), "test")
    with pytest.raises(DecodeError, match="SDK executable is unavailable"):
        decoder.decode(Path("relative/missing.jpg"), {})
