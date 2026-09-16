## 1. 설치 (Windows)

### 1-1. Git

1. https://git-scm.com/download/win 에서 설치 파일을 받는다.
2. 옵션은 전부 기본값으로 두고 Next 만 누른다.
3. 설치 후 확인한다.

```bash
git --version
```

### 1-2. Python 3.12

1. https://www.python.org/downloads/windows/ 에서 **3.12.x** 설치 파일을 받는다. 3.13 은 안 된다.
2. 설치 첫 화면에서 **"Add python.exe to PATH" 체크를 반드시 켠다.**
3. 설치 후 확인한다.

```bash
python --version
```

### 1-3. ffmpeg

PowerShell 을 열고:

```powershell
winget install Gyan.FFmpeg
```

설치 후 **PowerShell 창을 닫았다가 다시 열고** 확인한다.

```powershell
ffmpeg -version
ffprobe -version
```

`winget` 이 없으면 https://www.gyan.dev/ffmpeg/builds/ 에서
`ffmpeg-release-essentials.zip` 을 받아 압축을 풀고,
`bin` 폴더 경로를 시스템 환경변수 `Path` 에 추가한다.

### 1-4. 코드 받기

```powershell
git clone https://github.com/sfadfe/rateCV.git
cd rateCV
```

## 2. 설치 (Ubuntu / macOS)

```bash
# Ubuntu
sudo apt install git python3.12 python3.12-venv ffmpeg
# macOS
brew install git python@3.12 ffmpeg

git clone https://github.com/sfadfe/rateCV.git
cd rateCV
```

---

## 3. 영상 넣기

`data\raw` 폴더를 만들고 영상 파일을 넣는다.

인식하는 확장자: `.mp4` `.mov` `.m4v` `.avi` `.mkv` (대소문자 무관)

---

## 4. 클립 등록

`data\raw\clips.json` 을 만들고 영상 이름과 물 온도를 적는다.
실린더 위치와 눈금은 프로그램이 프레임을 보고 알아서 잰다.

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

| 칸 | 뜻 |
| --- | --- |
| `team` | 이름. zip 파일 이름에 들어간다 |
| `stem` | 영상 파일 이름 (확장자 제외). 대소문자까지 같아야 한다 |
| `T_C` | 물 온도 (°C) |

한 영상에 여러 실험을 이어 찍었으면 `stem` 을 같게 적는다. 적는 순서가 영상 순서다.
붓는 순간을 찾아 자동으로 나눈다.

`clips.json` 에 없는 영상이 `data\raw` 에 있으면 붙여넣을 줄을 그대로 찍어준다.

---

## 5. 실행

`run.bat` 을 더블클릭한다 (Ubuntu/macOS: `bash run.sh`).

- 처음엔 `.venv` 를 만들고 패키지를 받느라 몇 분 걸린다.
- 그다음 extract → measure → analyze → verify → pack 이 차례로 돈다.
- 끝나면 `results\` 와 이 폴더의 `submit_*.zip` 이 생긴다.

| 옵션 | 뜻 |
| --- | --- |
| `run.bat --force` | 프레임을 지우고 처음부터 다시 뽑는다 |
| `run.bat --no-video` | zip 에 영상을 넣지 않는다 (용량이 문제일 때) |

돌린 뒤 **`results\overlays\cal_*.jpg` 를 열어 눈금이 맞는지 확인한다.**
분홍 격자선이 유리에 찍힌 숫자와 겹쳐야 한다.

---

## 6. 결과 위치

| 경로 | 내용 |
| --- | --- |
| `results/summary.txt` | 클립별 `k`, R², RMSE, 전체 `Ea` |
| `results/timeseries.csv` | 프레임별 거품/액면 측정값 |
| `results/fig/fig_ln.png` | ln h – t |
| `results/fig/fig_ln_fit.png` | ln h – t + 적합 직선 |
| `results/fig/fig_arrhenius.png` | ln k – 1/T |
| `results/overlays/` | 검출선을 그려 넣은 검토용 이미지 |
| `results/provenance.jsonl` | 단계별 서명 기록 |
| `submit_*.zip` | 결과, 그래프, 프레임, 영상, `manifest.json` (파일별 sha256 과 서명) |

zip 은 그대로 둔다. 풀어서 다시 묶거나 안의 파일을 바꾸면 서명이 안 맞는다.

---

## 7. 자주 나는 오류

| 메시지 | 해결 |
| --- | --- |
| `Python 3.12 가 없다` | 1-2 를 다시 하고 `python --version` 확인 |
| `ffmpeg 가 없다` | 1-3 을 다시 하고 창을 새로 연다 |
| `영상 없음: ...\data\raw` | `data\raw` 에 영상을 넣는다 |
| `clips.json 를 못 읽었다` | 따옴표·쉼표·중괄호를 예시대로 |
| `clips.json 에 적힌 원본이 ... 에 없다` | `stem` 과 실제 파일 이름을 맞춘다 |
| `실험을 n개 찾았다 (clips.json 은 3개)` | 실험 사이에 관을 비우고 20 초 이상 두었는지 본다 |
| `h >= 35.0 mL 인 프레임이 없다` | 눈금을 잘못 읽었다. `results\overlays\cal_*.jpg` 로 확인한다 |
| `실린더를 못 찾았다` | 관이 프레임 안에 세로로 다 들어오는지 본다 |
| `받침을 못 찾았다` | 실린더 밑판이 프레임 아래쪽에 들어오게 다시 찍는다 |
| `눈금을 못 읽었다` / `눈금 적합이 나쁘다` | 눈금 숫자가 카메라 쪽을 보게 돌려 놓고 다시 찍는다 |
| `기록과 다른 파일이 있다` (pack) | `results` 나 `data\frames` 를 손댔다. `run.bat --force` |
| `WinError 32` (다른 프로세스가 사용 중) | `results\fig` 의 그림을 열어 둔 채 돌렸다. 닫고 다시 |
| `verify` 가 `코드 src/...` 에서 불일치 | git 이 줄바꿈을 CRLF 로 바꿨다. `git config core.autocrlf false` 후 다시 clone |
