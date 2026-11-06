# 무료 이미지 방식 검토 (2026-10-09)

## 이 PC

| 항목 | 확인 값 |
|---|---|
| GPU | AMD Radeon 840M 내장 그래픽 (RDNA 3.5, 전용 VRAM 없음 — 시스템 메모리 공유, Windows 표기 512MB) |
| NVIDIA/CUDA | 없음 (`nvidia-smi` 없음) |
| NPU | AMD XDNA 2 "NPU Compute Accelerator Device" (Ryzen AI 5 435, 제3자 사양표 기준 최대 50 TOPS) |
| CPU / RAM | Ryzen AI 5 435 6코어 / 31.2GB |

판단: **완전 자동 로컬 생성은 가능은 하지만 실용적이지 않다.** ComfyUI 는 AMD 를 DirectML(Windows) 또는 ROCm(WSL, 지원 GPU 한정)으로 돌릴 수 있지만,
내장 GPU 에서 SDXL 1장은 수 분 단위로 예상되고(840M 실측 자료 없음), 캐릭터 일관성용 LoRA 학습은 이 사양으로 어렵다.
AMD Amuse(무료)는 Ryzen AI NPU 로 SD 계열을 돌리지만 화면 조작용 앱이라 자동 연결 API 가 없고, 리뷰 기준 1장 70초 안팎.

## 모델 라이선스·캐릭터 참조

| 모델 | 상업 이용 | 참조 이미지(캐릭터 유지) | 이 PC |
|---|---|---|---|
| SD 1.5 (CreativeML OpenRAIL-M) | 가능 (사용 제한 조항 준수) | IP-Adapter·ControlNet reference | 느리지만 가능 |
| SDXL 1.0 (OpenRAIL++-M) | 가능, 매출 상한 없음 | IP-Adapter, LoRA | 매우 느림 |
| SD 3.5 (Stability Community License) | 연매출 100만 달러 미만 무료 | 제한적 | 어려움 |
| FLUX.1 schnell (Apache 2.0) | 가능 | Redux·IP-Adapter 계열 | 모델이 커서 사실상 불가 |
| FLUX.1 dev / Kontext dev | 비상업 라이선스 (별도 상업 라이선스 필요) | Kontext 는 참조 편집 강함 | 불가 |
| 커뮤니티 파인튜닝 모델 | 모델마다 다름 — 개별 확인 필수 | — | — |
| ChatGPT 이미지 (사용자 구독) | OpenAI 약관상 출력물 권리는 사용자에게 (정책 준수 조건) | 이미지 업로드로 참조 가능 | 비용 0원(이미 구독), 수동 |
| Gemini API | 유료 (장당 49~194원) | 참조 이미지 입력 | 보존, 기본 꺼짐 |

라이선스는 시점마다 바뀔 수 있으니 실제 사용 전 원문(Hugging Face 모델 카드·Stability AI·Black Forest Labs·OpenAI 약관)을 다시 확인한다.

## 추천 구성 (이번에 구현)

1. **기본 = 무료 조합 렌더링**: 햄토리치 투명 PNG 8종 + 코드로 그린 원근 장면 11종(원룸·거실·마트·은행·부동산·사무실·카페·거리·아파트·지하철·뉴스)
   + 시간대 하늘·조명 + 감정 효과 + 의인화 캐릭터(물가·월급·금리…) + 두 인물 컷 + 훅 표지.
2. **보강 = ChatGPT 그림 받은편지함**: `assets/inbox/` 에 `bg_원룸_밤.png`, `햄토리치_놀람_서있음.png` 처럼 넣으면 자동 등록
   (흰 배경 제거, 4:5 맞춤, 새 이름은 조연으로). 제작 시작 때 자동 실행, `characters import` 로도 실행.
3. **선택 = Gemini API**: `characters generate --confirm-cost` 일 때만 과금. 기본값은 무료(`images.provider: none`, `carousel.image_provider: none`).
4. **나중 = ComfyUI 연결**: NVIDIA 8GB 이상 GPU PC(또는 사용자가 띄운 ComfyUI 서버)가 생기면 ComfyUI HTTP API(`/prompt`, `/history`, `/view`)를
   이미지 provider 로 붙이는 방식이 가능하다. 지금 PC 에서는 속도 때문에 권하지 않아 구현하지 않았다.

## 출처
- ComfyUI (AMD/DirectML·저VRAM 오프로딩): https://github.com/comfyanonymous/ComfyUI
- AMD ROCm on WSL ComfyUI 가이드: https://rocm.blogs.amd.com/software-tools-optimization/rocm-on-wsl/README.html
- Radeon 840M 사양: https://notebookcheck.net/AMD-Radeon-840M-Benchmarks-and-Specs.950405.0.html
- Ryzen AI 5 435 NPU: https://laptopmedia.com/processor/amd-ryzen-ai-5-435/
- AMD Amuse: https://www.amd.com/en/blogs/2024/introducing-amuse-2-0-beta-with-amd-xdna-super-re.html , https://www.techradar.com/computing/artificial-intelligence/amds-new-ai-image-generator-for-windows-will-make-images-right-on-your-pc-forget-the-cloud
- Stability AI 라이선스: https://stability.ai/license
- FLUX.1 schnell / OpenFLUX (Apache 2.0): https://comfyui-wiki.com/en/news/2024-10-05-ostris-releases-openflux1
