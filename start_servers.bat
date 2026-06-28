@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================================
echo   🚀 启动 llama.cpp 本地模型服务
echo ===================================================================
echo.

set LLAMA_DIR=E:\AI_Models\Holo 3.1\llama-b9616-bin-win-cuda-13.3-x64
set TEXT_MODEL=E:\AI_Models\开源模型\Model\Hermes-3-Llama-3.1-8B.Q6_K.gguf
set VISION_MODEL=E:\AI_Models\开源模型\Model\Qwen2.5-VL-7B-Instruct-Q6_K.gguf
set MMPROJ=E:\AI_Models\开源模型\Model\mmproj-model-f16.gguf
set LLAMA_EXE=%LLAMA_DIR%\llama-server.exe

REM 检查 llama-server.exe 是否存在
if not exist "%LLAMA_EXE%" (
    echo ❌ llama-server.exe 未找到！
    echo    期望路径: %LLAMA_EXE%
    echo    请确认 llama.cpp 已正确放置在 %LLAMA_DIR%
    echo.
    echo    下载地址: https://github.com/ggml-org/llama.cpp/releases
    echo    选择 Windows x64 (CUDA 13) 版本
    pause
    exit /b 1
)

REM 检查模型文件
if not exist "%TEXT_MODEL%" (
    echo ❌ 文本模型未找到: %TEXT_MODEL%
    pause
    exit /b 1
)
if not exist "%VISION_MODEL%" (
    echo ❌ 视觉模型未找到: %VISION_MODEL%
    pause
    exit /b 1
)
if not exist "%MMPROJ%" (
    echo ❌ mmproj 文件未找到: %MMPROJ%
    pause
    exit /b 1
)

echo [1/2] 启动文本模型 (Hermes-3-Llama-3.1-8B) @ port 8080 ...
start "🤖 Text Model Server" "%LLAMA_EXE%" ^
    --model "%TEXT_MODEL%" ^
    --host 127.0.0.1 ^
    --port 8080 ^
    --n-gpu-layers 99 ^
    --ctx-size 8192 ^
    --log-disable

echo.
echo [2/2] 启动视觉模型 (Qwen2.5-VL-7B) @ port 8081 ...
start "👁️ Vision Model Server" "%LLAMA_EXE%" ^
    --model "%VISION_MODEL%" ^
    --mmproj "%MMPROJ%" ^
    --host 127.0.0.1 ^
    --port 8081 ^
    --n-gpu-layers 99 ^
    --ctx-size 4096 ^
    --log-disable

echo.
echo ===================================================================
echo   ⏳ 等待模型加载... (约 10-30 秒)
echo   文本模型: http://127.0.0.1:8080
echo   视觉模型: http://127.0.0.1:8081
echo ===================================================================
echo.

REM 等待模型加载
timeout /t 15 /nobreak >nul

REM 检查服务是否就绪
echo [检查] 文本模型服务...
curl -s http://127.0.0.1:8080/health >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  文本模型可能还在加载，稍后再试
) else (
    echo   ✅ 文本模型服务就绪
)

echo.
echo [检查] 视觉模型服务...
curl -s http://127.0.0.1:8081/health >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  视觉模型可能还在加载，稍后再试
) else (
    echo   ✅ 视觉模型服务就绪
)

echo.
echo ===================================================================
echo   ✅ 模型服务已启动！
echo   现在可以运行 start_agent.bat 启动 Agent
echo   关闭窗口将停止所有服务
echo ===================================================================
echo.
pause
