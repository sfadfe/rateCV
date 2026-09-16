## 1. 설치 (한 번만)

### Windows

1. **Python 3.12** — https://www.python.org/downloads/windows/ 에서 **3.12.x** 를 받는다. 3.13 이면 안 된다.
   설치 첫 화면에서 **"Add python.exe to PATH" 체크를 켠다.**
2. **ffmpeg** — PowerShell 에서:
   ```powershell
   winget install Gyan.FFmpeg
   ```
   설치 후 열려 있는 창을 전부 닫는다. (`winget` 이 없으면 https://www.gyan.dev/ffmpeg/builds/ 의
   `ffmpeg-release-essentials.zip` 을 풀고 `bin` 폴더를 환경변수 `Path` 에 추가.)

### Ubuntu / macOS

```bash
sudo apt install python3.12 python3.12-venv ffmpeg     # Ubuntu
brew install python@3.12 ffmpeg                        # macOS
```

## 2. 폴더

```
run.bat / run.sh      ← 이것만 실행
run.py                실행 순서 (extract → measure → analyze → verify → pack)
bin/                  실행되는 코드 (.pyc). 손대지 말 것
src/                  같은 코드의 읽기용 원본 (.py)
data/raw/             ← 영상 넣는 곳. clips.json 에 영상 이름·온도를 적는다
data/frames/          영상에서 뽑힌 프레임 (1초당 1장). 자동 생성
results/              결과가 여기 생긴다
requirements.txt      파이썬 패키지 판 고정
submit_*.zip          ← 실행이 끝나면 생긴다
```

## 3. 영상 넣기

1. `data/raw/` 에 영상을 넣는다 (확장자는 `.mp4` `.mov` 등 아무거나). 온도별로 따로 찍은 3개든, 한 번에 이어 찍은 1개든 된다.
2. `data/raw/clips.json` 을 메모장으로 열어 이름, 영상 파일 이름(확장자 빼고), 물 온도를 적는다.

따로 찍은 경우 (영상 3개):

```json
{
  "team": "이름",
  "clips": {
    "cold": {"stem": "20260824_142918", "T_C": 14.2},
    "rt":   {"stem": "20260824_144012", "T_C": 27.2},
    "hot":  {"stem": "20260824_142727", "T_C": 54.7}
  }
}
```

한 번에 이어 찍은 경우 (영상 1개, 얼음물 → 상온 → 물중탕 순): `stem` 에 같은 이름을 세 번 적는다.
**적는 순서가 영상에 나오는 순서**다. 붓는 장면을 알아서 찾아 세 구간으로 나눈다.

```json
{
  "team": "이름",
  "clips": {
    "cold": {"stem": "20260824_150000", "T_C": 14.2},
    "rt":   {"stem": "20260824_150000", "T_C": 27.2},
    "hot":  {"stem": "20260824_150000", "T_C": 54.7}
  }
}
```

이어 찍을 때 지킬 것: 카메라는 고정하고, 실험 사이에 관을 비우고 (관은 옮겨도 된다),
거품이 꺼지는 동안 카메라 앞을 5초 넘게 가리지 않는다. 화면이 크게 움직이는 곳(붓기·비우기)을 기준으로 나누기 때문이다.
| 칸 | 뜻 |
| --- | --- |
| `team` | 이름. zip 파일 이름에 들어간다 |
| `hot` `rt` `cold` | 클립 이름. 바꿔도 되고, 클립이 2개나 4개여도 된다 (온도가 서로 다른 클립 2개 이상) |
| `stem` | `data/raw` 의 영상 파일 이름에서 확장자를 뺀 것. 대소문자까지 같아야 한다 |
| `T_C` | 물 온도 (°C). 실험 기록에서 |

실린더 위치와 눈금은 프로그램이 프레임을 보고 알아서 잰다.

## 4. 실행

`run.bat` 을 더블클릭한다 (Ubuntu/macOS: `bash run.sh`).

- 처음엔 가상환경을 만들고 패키지를 받느라 몇 분 걸린다.
- 그다음 영상마다 1초당 1장씩 프레임을 뽑는다 (몇 분).
- 끝나면 창에 아래가 찍힌다.

```
===== analyze =====
54.7 °C: t0=4s  h0=79.5 mL  k=2.8562e-02 s^-1  n=68  R2=0.9534  RMSE=0.1239  오검출=9 보간=7
27.2 °C: ...
14.2 °C: ...
Ea = 32779.1 J/mol = 32.78 kJ/mol
Arrhenius R2 = 0.9642
provenance seq=3 tag=a1b2c3d4...

===== verify =====
seq=1 extract ...
  ok 서명
  ok 체인
  ok 코드 bin/extract.pyc
  ...
3 항목 — 전부 통과

===== pack =====
submit_이름_20260916-1030_ab12cd34.zip  1180 MB  파일 542개
manifest tag=ab12cd34...
```

| 옵션 | 뜻 |
| --- | --- |
| `run.bat --force` | 프레임을 지우고 처음부터 다시 뽑는다 |
| `run.bat --no-video` | zip 에 영상을 넣지 않는다 (용량이 문제일 때) |

## 5. 결과 읽는 법

| 파일 | 내용 |
| --- | --- |
| `results/summary.txt` | 온도별 k, R², RMSE, 전체 Ea |
| `results/timeseries.csv` | 프레임별 거품·액면 높이 |
| `results/fig/*.png` | ln h – t, 적합 직선, 아레니우스 그래프 |
| `results/overlays/cal_*.jpg` | 눈금 자동 인식 결과. 분홍 격자가 눈금 숫자와 겹쳐야 정상 |
| `results/overlays/ov_*.jpg` | 검출된 거품선(노랑)·액면(빨강) |
| `results/provenance.jsonl` | 단계별 서명 기록 |

**`results/overlays/cal_*.jpg` 는 반드시 눈으로 확인해라.** 격자가 눈금과 어긋나면 그 클립은 못 쓴다 (다시 찍어야 한다).

## 6. zip

`submit_<이름>_<날짜>_<서명>.zip` 안에는 이런 것이 들어 있다.

| 내용 | 왜 |
| --- | --- |
| `manifest.json` | 파일별 sha256 과 서명. 파일 하나라도 바뀌면 서명이 안 맞는다 |
| `results/` (CSV, summary, 그래프, 오버레이, provenance) | 결과와 그 기록 |
| `data/frames/` | 측정에 쓰인 프레임. 이 프레임으로 다시 돌리면 k·Ea 가 똑같이 나온다 |
| `data/raw/clips.json` + 영상 | 조건과 원본 |

하지 말 것:

- zip 을 풀어서 다시 묶기, zip 안의 파일 고치기 → 서명 불일치
- `src/` 의 `.py` 로 직접 돌리기 → 서명키가 없어 태그가 `unsigned` 로 찍힌다
- `results/` 나 `data/frames/` 의 파일을 손대고 나서 `run.bat` 다시 돌리기 → 기록과 달라 `pack` 이 거부한다
- `bin/` 바꾸기 → 코드 해시가 달라진다

값이 이상하면 파일을 고치지 말고 **영상을 다시 찍어서** `run.bat --force`.

## 7. 오류

| 메시지 | 해결 |
| --- | --- |
| `Python 3.12 가 없다` | 1번. 3.12 를 깔고 `python --version` 확인 |
| `ffmpeg 가 없다` | 1번. 깔고 나서 창을 새로 연다 |
| `영상 없음: ...data\raw` | 3번. 영상을 넣는다 |
| `clips.json 를 못 읽었다` | 3번. 따옴표·쉼표·중괄호를 예시대로 |
| `clips.json 에 적힌 원본이 ... 없다` | `stem` 과 실제 파일 이름(확장자 빼고)을 똑같이 |
| `실험을 n개 찾았다 (clips.json 은 3개)` | 이어 찍은 영상을 자동으로 못 나눴다. 실험 사이에 관을 비우고 20 초 이상 두었는지 본다 |
| `프레임이 있지만 서명된 추출 기록과 다르다 — 다시 뽑는다` | 프레임 폴더가 손댔거나 기록이 없다. 알아서 다시 뽑으니 그냥 두면 된다 |
| `h >= 35.0 mL 인 프레임이 없다` / `눈금을 못 읽었다` | 눈금 인식 실패. `cal_*.jpg` 확인. 눈금 숫자가 카메라를 보게 다시 찍는다 |
| `기록과 다른 파일이 있다` (pack) | 결과나 프레임을 손댔다. `run.bat --force` 로 처음부터 |
| `!! 서명 미서명` (verify) | `.py` 로 돌린 기록이 섞였다. `results/provenance.jsonl` 을 지우고 `run.bat --force` |
| `!! 코드 bin/...pyc` | `bin/` 이 바뀌었다. 패키지를 다시 받아라 |
| `WinError 32` | `results/fig` 의 그림을 열어 둔 채 돌렸다. 닫고 다시 |
