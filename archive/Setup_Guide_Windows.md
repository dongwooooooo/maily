# 신규 프로젝트 셋업 가이드 (VSCode + GitHub + Claude CLI)

macOS 기준. 새 맥/새 프로젝트에서 코드 한 줄도 없는 상태부터 "VSCode에서 폴더 열고 Claude CLI로 개발 시작" 까지 순서대로 진행하면 되도록 정리했다. YGTJ 프로젝트와 무관한 어떤 신규 프로젝트에도 동일하게 적용 가능.

---

## 0. 사전 확인

필요한 계정 세 개.

- GitHub 계정 (없으면 [github.com/signup](https://github.com/signup))
- Anthropic Console 계정 + 결제 카드 등록 ([console.anthropic.com](https://console.anthropic.com)) — Claude CLI 사용에 필요
- 애플 ID (App Store에서 Xcode Command Line Tools 다운로드용, 이미 로그인돼 있을 것)

---

## 1. macOS 기본 도구 설치

### 1-1. Xcode Command Line Tools

터미널(Spotlight → "터미널")에서:

```bash
xcode-select --install
```

팝업이 뜨면 "설치" 클릭. 5~15분 소요. `git`, `make`, 컴파일러가 함께 설치된다.

### 1-2. Homebrew (macOS 패키지 매니저)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

설치 끝나면 안내대로 PATH 등록. 애플 실리콘(M1~M4)이면 아래 두 줄을 `~/.zprofile` 에 추가하라고 나온다.

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

`brew --version` 이 뜨면 완료.

### 1-3. Node.js (Claude CLI 실행에 필요)

nvm 방식이 유연하다.

```bash
brew install nvm
mkdir -p ~/.nvm
echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.zshrc
echo '[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"' >> ~/.zshrc
source ~/.zshrc

nvm install --lts
nvm use --lts
node -v   # v20 이상이면 OK
```

### 1-4. VSCode

```bash
brew install --cask visual-studio-code
```

설치 후 VSCode 한 번 실행. Command Palette(⌘⇧P) → "Shell Command: Install 'code' command in PATH" 실행. 이후 어떤 터미널에서든 `code .` 로 현재 폴더를 VSCode로 연다.

### 1-5. GitHub CLI (선택이지만 강력 추천)

```bash
brew install gh
```

토큰 없이 브라우저 인증만으로 리포지토리 생성/PR 관리가 가능하다.

---

## 2. Git 사용자 설정

한 번만 하면 됨. 이메일은 GitHub 계정과 동일하게, 이름은 커밋에 표시될 이름으로.

```bash
git config --global user.name "Ryan"
git config --global user.email "hamletjins@gmail.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

프라이버시 이메일을 쓰고 싶다면 GitHub 설정에서 발급되는 `12345+hamletjins@users.noreply.github.com` 형식을 쓰면 이메일이 공개되지 않는다.

---

## 3. GitHub 인증

두 가지 방법. 하나만 선택.

### 방법 A: GitHub CLI (권장)

```bash
gh auth login
```

인터랙티브로 몇 가지 물어본다. 답 예시:

- Where do you use GitHub? → **GitHub.com**
- What is your preferred protocol for Git operations? → **HTTPS**
- Authenticate Git with your GitHub credentials? → **Y**
- How would you like to authenticate GitHub CLI? → **Login with a web browser**

브라우저가 열리고 코드를 붙여넣으면 끝. 이후 `git push` 도 자동으로 인증 처리.

### 방법 B: SSH 키

```bash
ssh-keygen -t ed25519 -C "hamletjins@gmail.com"
# Enter 세 번 (기본 경로, 빈 패스프레이즈)
eval "$(ssh-agent -s)"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
pbcopy < ~/.ssh/id_ed25519.pub
```

클립보드에 공개키가 복사됨. GitHub → Settings → SSH and GPG keys → New SSH key → 붙여넣기.

---

## 4. 프로젝트 폴더 생성 & Git 초기화

프로젝트 루트를 어디 둘지 결정. 관례상 `~/Documents/Projects/` 밑에 모으는 게 관리하기 쉽다.

```bash
mkdir -p ~/Documents/Projects/my-new-project
cd ~/Documents/Projects/my-new-project
code .
```

마지막 `code .` 로 VSCode가 이 폴더를 열면서 이후 작업은 VSCode 안에서 진행. **VSCode 상단 메뉴 → Terminal → New Terminal** (또는 `⌃`~) 로 통합 터미널을 연다. 이후 모든 명령은 이 통합 터미널에서 실행하면 된다.

### 4-1. 기본 파일

```bash
git init
```

`.gitignore` 를 먼저 만든다. 언어별 템플릿은 [github/gitignore](https://github.com/github/gitignore) 참고. 최소한 아래는 포함.

```bash
cat > .gitignore <<'EOF'
# macOS
.DS_Store

# 환경 변수
.env
.env.local
.env.*.local

# Node
node_modules/
dist/
build/
.next/
.vite/
*.log

# 에디터
.vscode/*
!.vscode/settings.json
!.vscode/extensions.json
.idea/

# 로컬 캐시
.cache/
tmp/
EOF
```

`README.md` 도 하나 만든다.

```bash
cat > README.md <<'EOF'
# my-new-project

프로젝트 한 줄 설명.

## 개발 시작

\`\`\`bash
# 여기에 설치/실행 명령
\`\`\`
EOF
```

`.env.local` 등 비밀값 파일이 필요하면 이 시점에 만들어둔다. `.gitignore` 에 이미 포함돼 있어 커밋 대상에서 자동 제외.

### 4-2. 첫 커밋

```bash
git add .
git commit -m "chore: 초기 프로젝트 스캐폴딩"
```

---

## 5. GitHub 리포지토리 생성 & 연결

### 방법 A: `gh` 로 원샷 (권장)

로컬 폴더에서:

```bash
gh repo create my-new-project --private --source=. --remote=origin --push
```

옵션 해설.

- `--private` : 프라이빗 리포. 팀 공유용이면 `--public` 로 바꿔도 됨.
- `--source=.` : 현재 폴더를 리포지토리 소스로 지정.
- `--remote=origin` : origin 리모트 자동 등록.
- `--push` : 첫 커밋을 즉시 푸시.

### 방법 B: 웹에서 만들고 수동 연결

1. github.com → 우상단 `+` → **New repository**
2. Repository name 입력, **Public/Private** 선택, README/gitignore/license 는 모두 **체크 안 함** (로컬에 이미 있음)
3. **Create repository** 클릭
4. 다음 명령을 로컬 터미널에서 실행:

```bash
git remote add origin https://github.com/<username>/my-new-project.git
git branch -M main
git push -u origin main
```

---

## 6. Claude CLI 설치 & 첫 실행

### 6-1. 설치

```bash
npm install -g @anthropic-ai/claude-code
claude --version   # 버전이 뜨면 성공
```

권한 오류가 나면 `sudo npm i -g @anthropic-ai/claude-code` 대신 npm 전역 폴더를 사용자 홈으로 옮기는 게 안전하다.

```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
source ~/.zshrc
npm install -g @anthropic-ai/claude-code
```

### 6-2. 로그인

```bash
claude login
```

Anthropic Console 로그인 페이지가 브라우저에 열리고, 인증하면 CLI가 자동으로 토큰을 받아 저장한다. API 결제 카드 등록이 안 돼 있으면 여기서 막히니 먼저 [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing) 에서 카드 등록.

### 6-3. 프로젝트 루트에서 첫 실행

VSCode 통합 터미널에서, 프로젝트 루트에서:

```bash
claude
```

Claude CLI가 대화형으로 뜬다. `/init` 을 입력하면 프로젝트를 스캔해서 `CLAUDE.md`(프로젝트 컨텍스트 파일)을 자동 생성한다.

첫 프롬프트 예시:

```
프로젝트 목적, 기술 스택, 개발 규칙을 정리한 CLAUDE.md 를 만들어줘.
```

### 6-4. CLI 종료 & 재진입

- 종료: `/exit` 또는 `Ctrl+D`
- 재진입: 프로젝트 루트에서 `claude` 다시 실행

---

## 7. VSCode 편의 확장

`⌘⇧X` (Extensions) 에서 아래 정도만 깔면 충분.

- **GitHub Pull Requests and Issues** (GitHub) — 리포 관리
- **GitLens** (GitKraken) — blame/history
- **ESLint** (Microsoft) — JS/TS 프로젝트
- **Prettier** (Prettier) — 포매팅
- 언어별: **Python**, **Go**, **Rust Analyzer** 등 필요한 것만

Claude Code 자체가 VSCode 확장으로도 있지만, CLI + 통합 터미널 조합이 훨씬 유연하다. 확장은 선택.

---

## 8. 하루 작업 흐름 (참고)

```bash
cd ~/Documents/Projects/my-new-project
code .                          # VSCode 오픈
# ─ VSCode 통합 터미널에서 ↓
git pull                        # 최신 상태 동기화
git checkout -b feat/새기능       # 브랜치
claude                          # Claude CLI 시작
# ─ Claude 세션에서 코드 짜기, /exit 후 ─
git status                      # 변경 확인
git add -A
git commit -m "feat: 새 기능 추가"
git push -u origin feat/새기능
gh pr create --fill             # PR 자동 생성
```

---

## 9. 자주 걸리는 함정

- **`command not found: claude`** → 6-1 의 PATH 설정 확인. `echo $PATH` 로 `~/.npm-global/bin` 포함 여부 체크.
- **`Permission denied (publickey)`** → SSH 방식인데 키가 GitHub에 등록 안 됨. `ssh -T git@github.com` 로 테스트.
- **`gh auth login` 이 브라우저를 못 여는 경우** → `--web` 대신 `--with-token` 로 [personal access token](https://github.com/settings/tokens) 을 파일로 전달.
- **커밋 이메일이 GitHub 프로필과 다른 경우** → GitHub Contribution 그래프에 안 나옴. `git config --global user.email` 값을 GitHub 등록 이메일 또는 noreply 이메일로 맞출 것.
- **`.env` 실수로 커밋** → `git rm --cached .env` 후 재커밋. 이미 원격에 올라갔다면 시크릿 로테이션 후 [git filter-repo](https://github.com/newren/git-filter-repo) 로 히스토리 정리.
- **Claude CLI 결제 이슈** → Anthropic 콘솔에서 크레딧 확인. 무료 크레딧 소진되면 CLI 호출이 401/402 를 리턴한다.
- **한글 파일명이 `??` 로 깨져 커밋됨** → 프로젝트 루트에서 `git config core.quotePath false` 실행.

---

## 10. 다음 단계

프로젝트 성격에 맞는 초기 스캐폴딩 명령 몇 개.

- React + Vite: `pnpm create vite@latest`
- Next.js: `pnpm create next-app`
- Python: `uv init` 또는 `poetry new`
- Node.js API: `pnpm init` 후 필요한 프레임워크 설치
- Supabase 백엔드: `npx supabase init`

여기까지 오면 실제 코드 작성 단계다. Claude CLI 안에서 "Vite + React + TypeScript + Tailwind 로 초기 스캐폴딩해줘" 같은 프롬프트로 시작하면 편하다.
