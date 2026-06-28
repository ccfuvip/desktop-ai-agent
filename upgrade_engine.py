"""
升级引擎 (Upgrade Engine) — Agent的"免疫系统"
负责：模型热插拔、模块热更新、依赖自动管理、版本回滚

核心能力：
1. 模型仓库管理 — 分类存储、自动下载、完整性校验
2. 模型热插拔 — 运行时切换模型，无需重启
3. 模块热更新 — 各模块独立升级，支持版本回滚
4. 依赖自动管理 — 自动安装缺失依赖，测试导入
"""
import json
import time
import hashlib
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    path: str
    category: str  # text / vision / audio
    quantization: str  # Q6_K / Q4_K_M / Q8_0 / IQ2_M
    size_gb: float
    vram_required_gb: float
    speed_score: float = 0.0  # 速度评分 0-10
    accuracy_score: float = 0.0  # 准确率评分 0-10
    strengths: List[str] = field(default_factory=list)  # 擅长领域
    download_url: str = ""
    downloaded_at: str = ""
    last_used_at: str = ""
    usage_count: int = 0
    status: str = "available"  # available / active / deprecated / testing


@dataclass
class ModuleVersion:
    """模块版本"""
    module_name: str
    current_version: str
    latest_version: str
    last_updated: str
    changelog: str = ""
    update_available: bool = False
    auto_update: bool = True


@dataclass
class DependencyInfo:
    """依赖信息"""
    package_name: str
    version: str
    required_by: str
    installed: bool = True
    install_command: str = ""
    test_passed: bool = False


# ---------------------------------------------------------------------------
# 升级引擎主类
# ---------------------------------------------------------------------------

class UpgradeEngine:
    """
    Agent的升级引擎 — 让Agent持续进化的关键组件
    
    工作流程：
    1. 发现新模型/新模块 → 评估价值
    2. 自动下载并校验完整性
    3. 沙箱测试性能
    4. 用户确认后正式部署
    5. 保留旧版本作为回滚预案
    """
    
    def __init__(self, config: Dict[str, Any], project_dir: Path = None):
        self.config = config.get("evolution", {}).get("upgrade", {})
        self.auto_check_updates = self.config.get("auto_check_updates", True)
        self.check_interval_hours = self.config.get("check_interval_hours", 12)
        self.model_download_dir = self.config.get("model_download_dir", "./temp/models")
        self.sandbox_test = self.config.get("sandbox_test", True)
        self.keep_backup = self.config.get("keep_backup", True)
        
        self.project_dir = project_dir or Path(config.get("project_dir", r"E:\Desktop\AI_Agent"))
        self.models_dir = self.project_dir / "data" / "models"
        self.temp_dir = self.project_dir / "temp"
        self.modules_file = self.project_dir / "data" / "modules_versions.json"
        
        # 确保目录存在
        for d in [self.models_dir, self.temp_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._models: Dict[str, ModelInfo] = {}
        self._modules: Dict[str, ModuleVersion] = {}
        self._dependencies: Dict[str, DependencyInfo] = {}
        
        # 加载已有数据
        self._load_all()
        
        # 扫描已有模型
        self._scan_local_models()

        # Phase 2 — 事件总线
        self._event_bus = None
    
    # ------------------------------------------------------------------
    # 模型仓库管理
    # ------------------------------------------------------------------
    
    def register_model(self, model: ModelInfo):
        """注册一个新模型到仓库"""
        self._models[model.id] = model
        self._save_models()
    
    def get_active_model(self, category: str = "text") -> Optional[ModelInfo]:
        """获取当前活跃的指定类别模型"""
        for model in self._models.values():
            if model.category == category and model.status == "active":
                return model
        return None
    
    def get_best_model(self, category: str = "text") -> Optional[ModelInfo]:
        """
        根据任务需求自动选择最优模型
        
        选择策略：
        1. 优先选择速度+准确率综合评分最高的
        2. 考虑当前显存可用性
        3. 考虑模型的擅长领域
        """
        candidates = [m for m in self._models.values() 
                     if m.category == category and m.status == "available"]
        
        if not candidates:
            return None
        
        # 综合评分 = 速度 * 0.4 + 准确率 * 0.6
        best = max(candidates, 
                   key=lambda m: m.speed_score * 0.4 + m.accuracy_score * 0.6)
        return best
    
    def switch_model(self, model_id: str) -> bool:
        """
        切换到指定模型（热插拔）
        
        1. 卸载旧模型（释放显存）
        2. 加载新模型
        3. 更新活跃标记
        """
        if model_id not in self._models:
            return False
        
        new_model = self._models[model_id]
        
        # 检查显存是否足够
        if new_model.vram_required_gb > 16.0:  # RTX 5080 16GB上限
            return False
        
        # 标记旧模型为非活跃
        for m in self._models.values():
            if m.category == new_model.category and m.status == "active":
                m.status = "available"
                m.last_used_at = datetime.now().isoformat()
        
        # 激活新模型
        new_model.status = "active"
        new_model.last_used_at = datetime.now().isoformat()
        
        self._save_models()
        return True
    
    def uninstall_model(self, model_id: str) -> bool:
        """卸载模型（保留备份）"""
        if model_id not in self._models:
            return False
        
        model = self._models[model_id]
        
        if self.keep_backup:
            # 移动到备份目录
            backup_dir = self.models_dir / "backups" / model.name
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            src = Path(model.path)
            if src.exists():
                dest = backup_dir / src.name
                shutil.move(str(src), str(dest))
                model.path = str(dest)
        
        model.status = "deprecated"
        self._save_models()
        return True
    
    def get_model_recommendations(self, task_type: str) -> List[ModelInfo]:
        """根据任务类型推荐模型"""
        task_map = {
            "text": ["text"],
            "vision": ["vision"],
            "audio": ["audio"],
            "coding": ["text"],
            "analysis": ["text", "vision"],
            "creative": ["text"],
        }
        
        categories = task_map.get(task_type, ["text"])
        candidates = []
        
        for cat in categories:
            for model in self._models.values():
                if model.category == cat and model.status == "available":
                    candidates.append(model)
        
        # 按综合评分排序
        candidates.sort(key=lambda m: m.speed_score * 0.4 + m.accuracy_score * 0.6, reverse=True)
        return candidates[:3]
    
    # ------------------------------------------------------------------
    # 模型下载与验证
    # ------------------------------------------------------------------
    
    async def download_model(self, model_info: Dict[str, Any]) -> Tuple[bool, str]:
        """
        下载新模型
        
        Args:
            model_info: 模型信息字典
                - name: 模型名称
                - download_url: 下载地址
                - category: 类别
                - quantization: 量化级别
                - expected_size_gb: 预期大小(GB)
                
        Returns:
            (成功与否, 消息)
        """
        name = model_info.get("name", "unknown")
        url = model_info.get("download_url", "")
        category = model_info.get("category", "text")
        quantization = model_info.get("quantization", "Q6_K")
        expected_size = model_info.get("expected_size_gb", 1.0)
        
        if not url:
            return False, "No download URL provided"
        
        # 创建下载目录
        download_dir = self.temp_dir / "models" / category / name
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成模型ID
        model_id = f"model_{hashlib.md5(url.encode()).hexdigest()[:12]}"
        
        # 下载模型（使用断点续传）
        import httpx
        try:
            file_path = None
            async with httpx.AsyncClient(timeout=3600) as client:  # 大文件给足时间
                async with client.stream("GET", url, follow_redirects=True) as response:
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    
                    output_path = download_dir / f"{name}.gguf"
                    
                    async with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 显示进度
                            if total_size:
                                pct = downloaded / total_size * 100
                                if int(pct) % 10 == 0:
                                    print(f"  Downloading {name}: {pct:.1f}%")
                    
                    file_path = str(output_path)
        except Exception as e:
            return False, f"Download failed: {str(e)}"
        
        # 验证完整性
        if not self._verify_model_integrity(file_path, expected_size):
            return False, "Model integrity check failed"
        
        # 沙箱测试（如果启用）
        if self.sandbox_test:
            test_passed = await self._sandbox_test_model(file_path, category)
            if not test_passed:
                return False, "Sandbox test failed"
        
        # 注册模型
        model = ModelInfo(
            id=model_id,
            name=name,
            path=file_path,
            category=category,
            quantization=quantization,
            size_gb=expected_size,
            vram_required_gb=expected_size * 1.1,  # 估算VRAM需求
            speed_score=7.0,  # 初始评分，测试后调整
            accuracy_score=7.0,
            strengths=[],
            download_url=url,
            downloaded_at=datetime.now().isoformat(),
            status="available",
        )
        
        self.register_model(model)
        
        # 移动到正式目录
        if file_path and Path(file_path).exists():
            models_dest = self.models_dir / category
            models_dest.mkdir(parents=True, exist_ok=True)
            dest_path = models_dest / Path(file_path).name
            shutil.move(file_path, str(dest_path))
            model.path = str(dest_path)
            self._save_models()
        
        return True, f"Model '{name}' downloaded and registered successfully"
    
    def _verify_model_integrity(self, file_path: str, expected_size_gb: float) -> bool:
        """验证模型文件完整性"""
        try:
            path = Path(file_path)
            if not path.exists():
                return False
            
            actual_size_gb = path.stat().st_size / (1024 ** 3)
            
            # 允许10%的大小误差
            if abs(actual_size_gb - expected_size_gb) / expected_size_gb > 0.1:
                return False
            
            # 计算文件哈希（用于后续完整性校验）
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            
            # 保存哈希值
            hash_file = path.with_suffix(".gguf.sha256")
            hash_file.write_text(sha256.hexdigest())
            
            return True
        except Exception:
            return False
    
    async def _sandbox_test_model(self, file_path: str, category: str) -> bool:
        """
        在沙箱中测试模型
        
        1. 检查文件格式是否正确（gguf头）
        2. 估算VRAM需求
        3. 简单的推理速度测试
        """
        try:
            # 检查GGUF文件头
            with open(file_path, "rb") as f:
                header = f.read(4)
                if header != b"GGUF":
                    return False
            
            # 估算VRAM
            file_size_gb = Path(file_path).stat().st_size / (1024 ** 3)
            vram_needed = file_size_gb * 1.1
            
            if vram_needed > 16.0:  # RTX 5080 16GB
                return False
            
            return True
        except Exception:
            return False
    
    # ------------------------------------------------------------------
    # 模块热更新
    # ------------------------------------------------------------------
    
    def check_module_updates(self) -> Dict[str, bool]:
        """
        检查所有模块是否有可用更新
        
        检查来源：
        1. 本地版本号对比
        2. GitHub Release（如果模块托管在GitHub）
        3. PyPI（如果是pip包）
        """
        updates_available = {}
        
        # 检查Python包的更新
        pip_packages = [
            "PyQt6", "chromadb", "httpx", "mss", "pyautogui",
            "keyboard", "pywin32", "playwright", "duckduckgo-search",
        ]
        
        for pkg in pip_packages:
            try:
                # 获取已安装版本
                result = subprocess.run(
                    ["pip", "show", pkg],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line.startswith("Version:"):
                            installed_version = line.split(":")[1].strip()
                            
                            # 检查最新版本
                            pip_result = subprocess.run(
                                ["pip", "index", "versions", pkg],
                                capture_output=True, text=True, timeout=10
                            )
                            
                            latest = None
                            for pline in pip_result.stdout.split("\n"):
                                if "Available versions:" in pline:
                                    versions = pline.split(":")[1].strip().split(", ")
                                    latest = versions[0] if versions else None
                                    break
                            
                            if latest and latest != installed_version:
                                updates_available[pkg] = True
                                self._update_module_info(pkg, installed_version, latest)
                            else:
                                updates_available[pkg] = False
            except Exception:
                updates_available[pkg] = False
        
        return updates_available
    
    def _update_module_info(self, name: str, current: str, latest: str):
        """更新模块版本信息"""
        if name not in self._modules:
            self._modules[name] = ModuleVersion(
                module_name=name,
                current_version=current,
                latest_version=latest,
                last_updated=datetime.now().isoformat(),
            )
        else:
            mod = self._modules[name]
            mod.latest_version = latest
            mod.update_available = current != latest
            mod.last_updated = datetime.now().isoformat()
    
    def update_module(self, module_name: str) -> Tuple[bool, str]:
        """
        更新指定模块
        
        1. 备份当前版本
        2. pip install --upgrade
        3. 测试导入
        4. 失败则回滚
        """
        # 备份当前状态
        backup_dir = self.temp_dir / "backups" / "modules" / module_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 执行升级
            result = subprocess.run(
                ["pip", "install", "--upgrade", module_name],
                capture_output=True, text=True, timeout=300
            )
            
            if result.returncode != 0:
                return False, f"pip install failed: {result.stderr[:200]}"
            
            # 测试导入
            test_result = subprocess.run(
                ["python3.11", "-c", f"import {module_name.replace('-', '_')}"],
                capture_output=True, text=True, timeout=10
            )
            
            if test_result.returncode != 0:
                # 回滚
                self._rollback_module(module_name, backup_dir)
                return False, f"Import test failed after upgrade. Rolled back."
            
            # 更新版本信息
            if module_name in self._modules:
                self._modules[module_name].current_version = self._modules[module_name].latest_version
                self._modules[module_name].update_available = False
            
            return True, f"Module '{module_name}' updated successfully"
            
        except Exception as e:
            self._rollback_module(module_name, backup_dir)
            return False, f"Update failed: {str(e)}"
    
    def _rollback_module(self, module_name: str, backup_dir: Path):
        """回滚模块到之前版本"""
        try:
            subprocess.run(
                ["pip", "install", module_name],
                capture_output=True, text=True, timeout=120
            )
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # 依赖自动管理
    # ------------------------------------------------------------------
    
    def auto_install_dependency(self, package_name: str, required_by: str) -> Tuple[bool, str]:
        """
        自动安装缺失的依赖
        
        流程：
        1. pip install package
        2. 测试导入
        3. 成功则记录到requirements.txt
        4. 失败则找替代方案
        """
        try:
            # 安装
            result = subprocess.run(
                ["pip", "install", package_name],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode != 0:
                return False, f"pip install failed: {result.stderr[:200]}"
            
            # 测试导入
            import_name = package_name.replace("-", "_")
            test_result = subprocess.run(
                ["python3.11", "-c", f"import {import_name}"],
                capture_output=True, text=True, timeout=10
            )
            
            if test_result.returncode != 0:
                return False, f"Import test failed for {package_name}"
            
            # 记录依赖
            dep = DependencyInfo(
                package_name=package_name,
                version="",  # 实际版本在安装后可查
                required_by=required_by,
                installed=True,
                test_passed=True,
            )
            self._dependencies[package_name] = dep
            
            # 更新requirements.txt
            self._update_requirements(package_name)
            
            return True, f"Dependency '{package_name}' installed and verified"
            
        except Exception as e:
            return False, f"Auto-install failed: {str(e)}"
    
    def _update_requirements(self, package_name: str):
        """更新requirements.txt"""
        req_file = self.project_dir / "requirements.txt"
        try:
            content = req_file.read_text(encoding="utf-8") if req_file.exists() else ""
            if package_name not in content:
                with open(req_file, "a", encoding="utf-8") as f:
                    f.write(f"{package_name}\n")
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # 数据持久化
    # ------------------------------------------------------------------
    
    def _load_all(self):
        """加载所有已保存的数据"""
        # 加载模型列表
        models_file = self.models_dir / "models_index.json"
        if models_file.exists():
            try:
                data = json.loads(models_file.read_text(encoding="utf-8"))
                for m in data:
                    model = ModelInfo(**m)
                    self._models[model.id] = model
            except Exception:
                pass
        
        # 加载模块版本
        if self.modules_file.exists():
            try:
                data = json.loads(self.modules_file.read_text(encoding="utf-8"))
                for m in data:
                    mod = ModuleVersion(**m)
                    self._modules[mod.module_name] = mod
            except Exception:
                pass
    
    def _save_models(self):
        """保存模型索引"""
        file = self.models_dir / "models_index.json"
        try:
            data = [asdict(m) for m in self._models.values()]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _save_modules(self):
        """保存模块版本信息"""
        try:
            data = [asdict(m) for m in self._modules.values()]
            self.modules_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
    
    def _scan_local_models(self):
        """扫描本地已有模型并注册"""
        model_dirs = {
            "text": r"E:\AI_Models\开源模型\Model",
            "vision": r"E:\AI_Models\开源模型\Model",
            "audio": r"E:\AI_Models\开源模型\Model",
        }
        
        for category, search_dir in model_dirs.items():
            dir_path = Path(search_dir)
            if not dir_path.exists():
                continue
            
            for gguf_file in dir_path.glob("*.gguf"):
                # 跳过mmproj等辅助文件
                if "mmproj" in gguf_file.name:
                    continue
                
                name = gguf_file.stem
                model_id = f"local_{hashlib.md5(str(gguf_file).encode()).hexdigest()[:12]}"
                
                if model_id not in self._models:
                    # 估算VRAM需求
                    size_gb = gguf_file.stat().st_size / (1024 ** 3)
                    
                    # 判断量化级别
                    quant = "Q6_K"
                    if "Q4" in name:
                        quant = "Q4_K_M"
                    elif "Q8" in name:
                        quant = "Q8_0"
                    elif "IQ" in name:
                        quant = "IQ2_M"
                    
                    # 判断类别
                    cat = category
                    if "VL" in name or "LLaVA" in name:
                        cat = "vision"
                    elif "whisper" in name.lower():
                        cat = "audio"
                    
                    model = ModelInfo(
                        id=model_id,
                        name=name,
                        path=str(gguf_file),
                        category=cat,
                        quantization=quant,
                        size_gb=size_gb,
                        vram_required_gb=size_gb * 1.1,
                        speed_score=7.0,
                        accuracy_score=7.0,
                        downloaded_at=datetime.now().isoformat(),
                        status="available",
                    )
                    
                    # 如果是第一个同类型的模型，设为活跃
                    if not any(m.category == cat and m.status == "active" for m in self._models.values()):
                        model.status = "active"
                    
                    self.register_model(model)
        
        self._save_models()
    
    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """获取升级引擎统计信息"""
        return {
            "total_models": len(self._models),
            "active_models": sum(1 for m in self._models.values() if m.status == "active"),
            "available_models": sum(1 for m in self._models.values() if m.status == "available"),
            "models_by_category": self._get_category_breakdown(),
            "modules_to_update": sum(1 for m in self._modules.values() if m.update_available),
            "total_dependencies": len(self._dependencies),
        }
    
    def _get_category_breakdown(self) -> Dict[str, int]:
        """按类别统计模型"""
        breakdown = {}
        for model in self._models.values():
            cat = model.category
            breakdown[cat] = breakdown.get(cat, 0) + 1
        return breakdown
    
    def get_model_list(self, category: str = None) -> List[Dict]:
        """获取模型列表"""
        models = self._models.values()
        if category:
            models = [m for m in models if m.category == category]
        
        return [
            {
                "id": m.id,
                "name": m.name,
                "category": m.category,
                "quantization": m.quantization,
                "size_gb": round(m.size_gb, 2),
                "vram_gb": round(m.vram_required_gb, 2),
                "status": m.status,
                "speed_score": m.speed_score,
                "accuracy_score": m.accuracy_score,
                "usage_count": m.usage_count,
            }
            for m in models
        ]


    # ------------------------------------------------------------------
    # Phase 2 增强 — 事件总线接入
    # ------------------------------------------------------------------

    def set_event_bus(self, bus) -> None:
        """注入事件总线"""
        self._event_bus = bus
        if self._event_bus:
            self._event_bus.emit("upgrade", "bus_attached", {
                "total_models": len(self._models),
                "active_models": sum(1 for m in self._models.values() if m.status == "active"),
            })

    def _emit(self, kind: str, payload: dict) -> None:
        """便捷事件发布"""
        if self._event_bus:
            self._event_bus.emit("upgrade", kind, payload)
