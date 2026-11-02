"""Tirar o fundo: original + mascara viram um video com transparencia do tamanho da mascara."""
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import alpha  # noqa: E402


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def test_compor_webm_e_mov():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        # Original a 30 fps em 640x360; mascara como o efeito a devolve: 24 fps, 544x320, 25 quadros.
        _ff("-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2", "-pix_fmt", "yuv420p", str(d / "orig.mp4"))
        _ff("-f", "lavfi", "-i", "color=white:size=544x320:rate=24:duration=2", "-frames:v", "25",
            "-pix_fmt", "yuv420p", str(d / "mascara.mp4"))
        for formato, campo in (("webm", "alpha_mode"), ("mov", None)):
            saida = alpha.compor(str(d / "orig.mp4"), str(d / "mascara.mp4"), d / f"out.{formato}", formato)
            info = json.loads(subprocess.run(
                ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                 "stream=width,height,nb_read_frames,pix_fmt:stream_tags", "-of", "json", str(saida)],
                capture_output=True, text=True).stdout)["streams"][0]
            assert (info["width"], info["height"], int(info["nb_read_frames"])) == (544, 320, 25)
            if campo:  # VP9 guarda o alfa a parte e marca com alpha_mode=1
                assert info.get("tags", {}).get("alpha_mode") == "1", info
            else:
                assert "a" in info["pix_fmt"].replace("yuv", ""), info


def test_ajustes_mudam_a_mascara():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        _ff("-f", "lavfi", "-i", "color=red:size=320x240:rate=24:duration=1", "-pix_fmt", "yuv420p", str(d / "orig.mp4"))
        # Mascara: quadrado branco no meio, borda cinza 50%.
        _ff("-f", "lavfi", "-i", "color=black:size=320x240:rate=24:duration=1", "-vf",
            "drawbox=x=100:y=60:w=120:h=120:color=gray:t=fill,drawbox=x=110:y=70:w=100:h=100:color=white:t=fill",
            "-frames:v", "9", "-pix_fmt", "yuv420p", str(d / "mascara.mp4"))
        def alfa_media(aj):
            s = alpha.compor(str(d / "orig.mp4"), str(d / "mascara.mp4"),
                             alpha.nome_saida(d / "out", "mov", aj), "mov", aj)
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(s), "-frames:v", "1", "-vf",
                                  "alphaextract,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
            return sum(raw) / len(raw)
        base = alfa_media(alpha.Ajustes())
        assert alfa_media(alpha.Ajustes(borda=-4)) < base < alfa_media(alpha.Ajustes(borda=4))
        assert alfa_media(alpha.Ajustes(preto=0.6)) < base  # o cinza da borda some
        assert alfa_media(alpha.Ajustes(inverter=True)) > 128
        assert alpha.nome_saida(d / "out", "webm", alpha.Ajustes()).name == "out.webm"
        assert alpha.nome_saida(d / "out", "webm", alpha.Ajustes(borda=2)).name != "out.webm"
