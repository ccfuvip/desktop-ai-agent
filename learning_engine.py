"""
学习引擎 (Learning Engine) — Agent的"大脑皮层"
负责：互联网知识学习、技能习得、插件发现、Agent互学

核心能力：
1. 互联网知识学习 — 主动搜索、抓取、理解、存储新知识
2. 技能习得 — 从重复任务中抽象出通用技能
3. 插件发现 — 扫描MCP Registry、GitHub发现新工具
4. Agent互学 — 从其他Agent学习技能和经验
"""
import json
import time
import hashlib
import asyncio
import httpx
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeItem:
    """一条知识条目"""
    id: str
    title: str
    content: str
    category: str  # tech / news / tutorial / tool / framework
    source: str    # url / platform
    tags: List[str] = field(default_factory=list)
    learned_at: str = ""
    expires_at: str = ""  # 知识有效期
    confidence: float = 1.0  # 置信度 0-1
    usage_count: int = 0  # 被使用次数
    success_rate: float = 1.0  # 使用成功率


@dataclass
class SkillEntry:
    """一个习得的技能"""
    id: str
    name: str
    description: str
    trigger_pattern: str  # 什么情况下触发此技能
    steps: List[str]  # 技能执行步骤
    tools_needed: List[str]  # 需要的工具
    success_rate: float = 1.0
    created_at: str = ""
    last_used_at: str = ""
    usage_count: int = 0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginEntry:
    """一个发现的插件/MCP Server"""
    id: str
    name: str
    description: str
    type: str  # mcp_server / pip_package / api_service / browser_extension
    source: str
    compatibility: float = 1.0  # 兼容性评分
    requires_install: bool = True
    install_command: str = ""
    test_passed: bool = False
    added_at: str = ""


@dataclass
class LearningRecord:
    """学习记录"""
    timestamp: str
    action: str  # search / learn / forget / verify
    subject: str
    result: str  # success / partial / failed
    details: str
    duration_sec: float = 0.0


# ---------------------------------------------------------------------------
# 学习引擎主类
# ---------------------------------------------------------------------------

class LearningEngine:
    """
    Agent的学习引擎 — 让Agent持续成长的核心组件
    
    工作流程：
    1. 遇到不会的问题 → 触发知识搜索
    2. 发现知识缺口 → 主动搜索互联网
    3. 理解并存储新知识 → 结构化存入ChromaDB
    4. 在实际任务中验证 → 更新置信度和经验
    5. 定期反思 → 淘汰过期知识，优化知识结构
    """
    
    def __init__(self, config: Dict[str, Any], memory_store=None):
        self.config = config.get("evolution", {}).get("learning", {})
        self.auto_learn = self.config.get("auto_learn", True)
        self.learn_interval_hours = self.config.get("learn_interval_hours", 24)
        self.search_engines = self.config.get("search_engines", ["duckduckgo", "bing"])
        self.knowledge_sources = self.config.get("knowledge_sources", [])
        self.max_knowledge_items = self.config.get("max_knowledge_items", 50000)
        
        self.memory_store = memory_store
        self.project_dir = Path(config.get("project_dir", r"E:\Desktop\AI_Agent"))
        
        # 数据存储路径
        self.skills_dir = self.project_dir / "data" / "skills"
        self.plugins_dir = self.project_dir / "data" / "plugins"
        self.knowledge_dir = self.project_dir / "data" / "knowledge"
        self.logs_dir = self.project_dir / "data" / "logs"
        
        # 确保目录存在
        for d in [self.skills_dir, self.plugins_dir, self.knowledge_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._knowledge_cache: Dict[str, KnowledgeItem] = {}
        self._skills_cache: Dict[str, SkillEntry] = {}
        self._plugins_cache: Dict[str, PluginEntry] = {}
        self._learning_records: List[LearningRecord] = []
        
        # 知识过期时间（天）
        self._expiry_days = {
            "tech": 90,
            "news": 7,
            "tutorial": 180,
            "tool": 365,
            "framework": 180,
        }
        
        # 加载已有数据
        self._load_all()

        # Phase 2 — 事件总线
        self._event_bus = None
    
    # ------------------------------------------------------------------
    # 互联网知识学习
    # ------------------------------------------------------------------
    
    async def search_and_learn(self, query: str, categories: List[str] = None) -> Dict[str, Any]:
        """
        主动搜索互联网并学习新知识
        
        Args:
            query: 搜索关键词或问题
            categories: 知识类别
            
        Returns:
            学习结果摘要
        """
        start_time = time.time()
        self._log_action("search", query, "started", f"Searching: {query}")
        
        results = {
            "query": query,
            "sources_hit": [],
            "knowledge_items": [],
            "skills_discovered": [],
            "errors": [],
        }
        
        # Step 1: 先检查记忆中是否已有相关知识
        existing = await self._check_memory(query)
        if existing and existing.get("confidence", 0) > 0.8:
            self._log_action("search", query, "success", "Found existing knowledge")
            return {
                "found_in_memory": True,
                "existing_confidence": existing.get("confidence"),
                "existing_content": existing.get("content", "")[:500],
            }
        
        # Step 2: 按搜索引擎依次搜索
        for engine in self.search_engines:
            try:
                engine_results = await self._search_engine(engine, query)
                results["sources_hit"].append(engine)
                if engine_results:
                    # Step 3: 理解并提取知识
                    knowledge = await self._extract_knowledge(engine_results, query, categories)
                    results["knowledge_items"].extend(knowledge)
            except Exception as e:
                results["errors"].append(f"{engine}: {str(e)}")
        
        # Step 4: 验证和内化新知识
        for item in results["knowledge_items"]:
            validated = await self._verify_and_internalize(item)
            if validated:
                self._knowledge_cache[item["id"]] = item
        
        # Step 5: 更新记忆
        if self.memory_store and results["knowledge_items"]:
            await self.memory_store.add_memories(results["knowledge_items"])
        
        duration = time.time() - start_time
        self._log_action("search", query, "success" if results["knowledge_items"] else "partial",
                        f"Learned {len(results['knowledge_items'])} items in {duration:.1f}s")
        
        return {
            "found_in_memory": False,
            "items_learned": len(results["knowledge_items"]),
            "sources_hit": results["sources_hit"],
            "errors": results["errors"],
            "duration_sec": duration,
        }
    
    async def _search_engine(self, engine: str, query: str) -> List[Dict]:
        """
        通过指定搜索引擎搜索
        
        2026年最新方案：
        - DuckDuckGo: 免费，无需API key
        - Bing: 需要API key，结果更准确
        - arXiv: 学术论文
        - GitHub: 代码相关搜索
        """
        results = []
        
        if engine == "duckduckgo":
            results = await self._search_duckduckgo(query)
        elif engine == "bing":
            results = await self._search_bing(query)
        elif engine == "arxiv":
            results = await self._search_arxiv(query)
        elif engine == "github":
            results = await self._search_github(query)
        
        return results
    
    async def _search_duckduckgo(self, query: str) -> List[Dict]:
        """使用DuckDuckGo搜索（免费，无需API）"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                )
                # 简单解析HTML（实际项目中可用better-html或parsel）
                import re
                links = re.findall(r'<a class="result__a" href="(.*?)"[^>]*>(.*?)</a>', resp.text)
                snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', resp.text)
                
                results = []
                for i, ((url, title)) in enumerate(links[:10]):
                    results.append({
                        "title": title.strip(),
                        "url": url,
                        "snippet": snippets[i].strip() if i < len(snippets) else "",
                        "source": "duckduckgo",
                    })
                return results
        except Exception as e:
            return []
    
    async def _search_bing(self, query: str) -> List[Dict]:
        """使用Bing搜索（需要API key）"""
        import os
        api_key = os.environ.get("BING_SEARCH_API_KEY", "")
        if not api_key:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    params={"q": query, "count": 10},
                    headers={"Ocp-Apim-Subscription-Key": api_key},
                )
                data = resp.json()
                results = []
                for page in data.get("webPages", {}).get("value", [])[:10]:
                    results.append({
                        "title": page.get("name", ""),
                        "url": page.get("url", ""),
                        "snippet": page.get("snippet", ""),
                        "source": "bing",
                    })
                return results
        except Exception:
            return []
    
    async def _search_arxiv(self, query: str) -> List[Dict]:
        """搜索arXiv学术论文"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={"search_query": f"all:{query}", "max_results": 5},
                )
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                
                results = []
                for entry in root.findall("atom:entry", ns):
                    title = entry.find("atom:title", ns).text.strip()
                    summary = entry.find("atom:summary", ns).text.strip()
                    link = entry.find("atom:id", ns).text
                    published = entry.find("atom:published", ns).text
                    
                    results.append({
                        "title": title,
                        "url": link,
                        "snippet": summary[:500],
                        "source": "arxiv",
                        "published": published,
                    })
                return results
        except Exception:
            return []
    
    async def _search_github(self, query: str) -> List[Dict]:
        """搜索GitHub项目"""
        import os
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": 5},
                    headers={"Authorization": f"token {token}"},
                )
                data = resp.json()
                results = []
                for repo in data.get("items", [])[:5]:
                    results.append({
                        "title": repo.get("full_name", ""),
                        "url": repo.get("html_url", ""),
                        "snippet": repo.get("description", "") or "",
                        "source": "github",
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language", ""),
                    })
                return results
        except Exception:
            return []
    
    async def _extract_knowledge(self, search_results: List[Dict], query: str,
                                  categories: List[str] = None) -> List[Dict]:
        """
        从搜索结果中提取结构化知识
        
        2026年最新方案：
        - 使用LLM理解搜索结果（比正则提取更准确）
        - 自动分类和打标签
        - 去重和重要性排序
        """
        knowledge_items = []
        
        for result in search_results:
            # 生成唯一ID
            content_hash = hashlib.md5(
                f"{result.get('url', '')}:{result.get('title', '')}".encode()
            ).hexdigest()[:12]
            
            # 确定类别
            category = self._classify_content(result, categories)
            
            # 计算过期时间
            expiry = self._expiry_days.get(category, 90)
            
            item = {
                "id": f"knowledge_{content_hash}",
                "title": result.get("title", ""),
                "content": result.get("snippet", "") + "\n\n" + result.get("url", ""),
                "category": category,
                "source": result.get("source", "web"),
                "url": result.get("url", ""),
                "tags": self._generate_tags(result, category),
                "learned_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(days=expiry)).isoformat(),
                "confidence": 0.7,  # 初始置信度，验证后提高
                "usage_count": 0,
                "success_rate": 1.0,
            }
            knowledge_items.append(item)
        
        return knowledge_items
    
    def _classify_content(self, result: Dict, categories: List[str] = None) -> str:
        """根据内容特征分类"""
        url = result.get("url", "").lower()
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        
        combined = url + " " + title + " " + snippet
        
        if "arxiv" in url or "paper" in title:
            return "tech"
        elif "github" in url:
            return "tool"
        elif "tutorial" in combined or "how to" in combined or "guide" in combined:
            return "tutorial"
        elif "news" in url or "blog" in url or "reddit" in url or "hacker news" in combined:
            return "news"
        elif "api" in combined or "sdk" in combined or "library" in combined:
            return "tool"
        else:
            return "tech"
    
    def _generate_tags(self, result: Dict, category: str) -> List[str]:
        """生成标签"""
        tags = [category]
        url = result.get("url", "").lower()
        
        if "python" in url or "python" in result.get("title", "").lower():
            tags.append("python")
        if "javascript" in url or "node" in url:
            tags.append("javascript")
        if "llm" in url or "ai" in url or "machine learning" in url:
            tags.append("ai")
        if "mcp" in url or "model context protocol" in url:
            tags.append("mcp")
        
        return tags
    
    async def _verify_and_internalize(self, item: Dict) -> bool:
        """
        验证和内化新知识
        
        1. 尝试在实际任务中使用
        2. 记录成功/失败
        3. 更新置信度
        """
        try:
            # 模拟验证（实际项目中会在这里调用LLM进行知识验证）
            # 这里简化为：如果内容有实质性内容就认为验证通过
            content = item.get("content", "")
            if len(content) > 50:  # 有一定内容量
                item["confidence"] = min(1.0, item.get("confidence", 0.7) + 0.2)
                self._knowledge_cache[item["id"]] = item
                self._save_knowledge_item(item)
                return True
            return False
        except Exception:
            return False
    
    # ------------------------------------------------------------------
    # 技能习得
    # ------------------------------------------------------------------
    
    def learn_skill_from_experience(self, task_description: str, steps_taken: List[str],
                                     success: bool) -> Optional[SkillEntry]:
        """
        从实际操作经验中学习新技能
        
        当Agent遇到反复出现的任务模式时，自动抽象出通用技能。
        
        Args:
            task_description: 任务描述
            steps_taken: 实际执行的步骤列表
            success: 任务是否成功
            
        Returns:
            新习得的技能，如果无法抽象则返回None
        """
        if not success:
            return None
        
        if len(steps_taken) < 2:
            return None
        
        # 分析步骤模式
        skill = self._analyze_pattern(steps_taken, task_description)
        if skill:
            skill.id = f"skill_{hashlib.md5(skill.name.encode()).hexdigest()[:8]}"
            skill.created_at = datetime.now().isoformat()
            skill.last_used_at = skill.created_at
            skill.usage_count = 1
            skill.success_rate = 1.0
            self._skills_cache[skill.id] = skill
            self._save_skill(skill)
            self._log_action("learn_skill", skill.name, "success",
                           f"Learned from {len(steps_taken)} steps")
            return skill
        
        return None
    
    def _analyze_pattern(self, steps: List[str], task_desc: str) -> Optional[SkillEntry]:
        """分析操作步骤，抽象出通用技能"""
        # 简化版模式识别
        # 实际项目中可以用LLM来分析步骤模式
        
        # 提取工具使用
        tools = set()
        for step in steps:
            step_lower = step.lower()
            if "click" in step_lower or "mouse" in step_lower:
                tools.add("mouse")
            if "type" in step_lower or "keyboard" in step_lower:
                tools.add("keyboard")
            if "window" in step_lower or "focus" in step_lower:
                tools.add("window")
            if "browser" in step_lower or "playwright" in step_lower:
                tools.add("browser")
            if "file" in step_lower or "read" in step_lower or "write" in step_lower:
                tools.add("file")
        
        if not tools:
            return None
        
        return SkillEntry(
            id="",
            name=f"auto_{task_desc[:30].replace(' ', '_')}",
            description=f"从经验中学到的技能: {task_desc}",
            trigger_pattern=task_desc,
            steps=steps,
            tools_needed=list(tools),
        )
    
    def get_recommended_skill(self, task_description: str) -> Optional[SkillEntry]:
        """根据任务描述推荐已有技能"""
        task_lower = task_description.lower()
        
        best_match = None
        best_score = 0
        
        for skill in self._skills_cache.values():
            # 简单的相关性匹配
            score = 0
            for tag in task_lower.split():
                if len(tag) > 3 and tag in skill.trigger_pattern.lower():
                    score += 1
                if skill.usage_count > 0:
                    score += skill.usage_count * 0.1
            
            if score > best_score:
                best_score = score
                best_match = skill
        
        if best_match and best_score >= 1:
            best_match.usage_count += 1
            best_match.last_used_at = datetime.now().isoformat()
            return best_match
        
        return None
    
    # ------------------------------------------------------------------
    # 插件发现
    # ------------------------------------------------------------------
    
    async def discover_plugins(self, sources: List[str] = None) -> List[PluginEntry]:
        """
        主动发现新插件/MCP Server
        
        扫描：
        1. MCP Registry
        2. GitHub Trending
        3. PyPI 新包
        """
        if sources is None:
            sources = self.knowledge_sources
        
        discovered = []
        
        for source in sources:
            try:
                if source == "github_trending":
                    plugins = await self._scan_github_trending()
                    discovered.extend(plugins)
                elif source == "mcp_registry":
                    plugins = await self._scan_mcp_registry()
                    discovered.extend(plugins)
            except Exception as e:
                self._log_action("discover_plugin", source, "failed", str(e))
        
        return discovered
    
    async def _scan_mcp_registry(self) -> List[PluginEntry]:
        """扫描MCP Registry发现新Server"""
        plugins = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://registry.modelcontextprotocol.io/servers.json",
                )
                servers = resp.json()
                
                for server in servers[:10]:  # 取前10个
                    plugin = PluginEntry(
                        id=f"mcp_{hashlib.md5(server.get('name', '').encode()).hexdigest()[:8]}",
                        name=server.get("name", ""),
                        description=server.get("description", ""),
                        type="mcp_server",
                        source="mcp_registry",
                        compatibility=server.get("stars", 0) / 1000.0,  # 简化的兼容评分
                        added_at=datetime.now().isoformat(),
                    )
                    plugins.append(plugin)
        except Exception:
            pass
        
        return plugins
    
    async def _scan_github_trending(self) -> List[PluginEntry]:
        """扫描GitHub Trending发现新工具"""
        plugins = []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": "agent OR mcp OR automation",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 5,
                    },
                    headers={"User-Agent": "AI-Agent/1.0"},
                )
                data = resp.json()
                
                for repo in data.get("items", [])[:5]:
                    plugin = PluginEntry(
                        id=f"github_{repo.get('id', 0)}",
                        name=repo.get("full_name", ""),
                        description=repo.get("description", ""),
                        type="mcp_server" if "mcp" in repo.get("name", "").lower() else "pip_package",
                        source="github_trending",
                        compatibility=min(1.0, repo.get("stargazers_count", 0) / 10000.0),
                        install_command=f"pip install {repo.get('name', '')}",
                        added_at=datetime.now().isoformat(),
                    )
                    plugins.append(plugin)
        except Exception:
            pass
        
        return plugins
    
    # ------------------------------------------------------------------
    # 数据持久化
    # ------------------------------------------------------------------
    
    def _load_all(self):
        """加载所有已保存的数据"""
        # 加载技能
        skills_file = self.skills_dir / "skills.json"
        if skills_file.exists():
            try:
                data = json.loads(skills_file.read_text(encoding="utf-8"))
                for s in data:
                    skill = SkillEntry(**s)
                    self._skills_cache[skill.id] = skill
            except Exception:
                pass
        
        # 加载插件
        plugins_file = self.plugins_dir / "plugins.json"
        if plugins_file.exists():
            try:
                data = json.loads(plugins_file.read_text(encoding="utf-8"))
                for p in data:
                    plugin = PluginEntry(**p)
                    self._plugins_cache[plugin.id] = plugin
            except Exception:
                pass
        
        # 加载知识
        knowledge_file = self.knowledge_dir / "knowledge_index.json"
        if knowledge_file.exists():
            try:
                data = json.loads(knowledge_file.read_text(encoding="utf-8"))
                for k in data:
                    item = KnowledgeItem(**k)
                    self._knowledge_cache[item.id] = item
            except Exception:
                pass
        
        # 加载学习记录
        records_file = self.logs_dir / "learning_records.json"
        if records_file.exists():
            try:
                data = json.loads(records_file.read_text(encoding="utf-8"))
                for r in data:
                    self._learning_records.append(LearningRecord(**r))
            except Exception:
                pass
    
    def _save_knowledge_item(self, item: Dict):
        """保存单个知识条目"""
        file = self.knowledge_dir / "knowledge_index.json"
        try:
            data = []
            if file.exists():
                data = json.loads(file.read_text(encoding="utf-8"))
            data.append(item)
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _save_skill(self, skill: SkillEntry):
        """保存技能"""
        file = self.skills_dir / "skills.json"
        try:
            data = list(self._skills_cache.values())
            file.write_text(json.dumps([asdict(s) for s in data], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _save_plugins(self):
        """保存插件列表"""
        file = self.plugins_dir / "plugins.json"
        try:
            data = list(self._plugins_cache.values())
            file.write_text(json.dumps([asdict(p) for p in data], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _log_action(self, action: str, subject: str, result: str, details: str = ""):
        """记录学习行为"""
        record = LearningRecord(
            timestamp=datetime.now().isoformat(),
            action=action,
            subject=subject,
            result=result,
            details=details,
        )
        self._learning_records.append(record)
        
        # 保持最近1000条记录
        if len(self._learning_records) > 1000:
            self._learning_records = self._learning_records[-1000:]
        
        # 持久化
        try:
            file = self.logs_dir / "learning_records.json"
            file.write_text(
                json.dumps([asdict(r) for r in self._learning_records], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # 定期学习（定时任务）
    # ------------------------------------------------------------------
    
    async def periodic_learning(self):
        """
        定期主动学习 — 每天凌晨执行
        
        扫描：
        1. GitHub Trending新工具
        2. MCP Registry新Server
        3. 技术博客新文章
        4. 过期知识清理
        """
        self._log_action("periodic_learn", "scheduled", "started", "Starting periodic learning")
        
        # 发现新插件
        plugins = await self.discover_plugins(["github_trending", "mcp_registry"])
        for p in plugins:
            if p.id not in self._plugins_cache:
                self._plugins_cache[p.id] = p
        
        # 清理过期知识
        expired = self._cleanup_expired_knowledge()
        
        # 保存更新
        self._save_plugins()
        
        self._log_action("periodic_learn", "completed", "success",
                        f"Discovered {len(plugins)} plugins, removed {expired} expired items")
        
        return {
            "plugins_discovered": len(plugins),
            "expired_removed": expired,
        }
    
    def _cleanup_expired_knowledge(self) -> int:
        """清理过期知识"""
        now = datetime.now()
        removed = 0
        
        to_remove = []
        for item_id, item in self._knowledge_cache.items():
            if item.expires_at:
                expire_date = datetime.fromisoformat(item.expires_at)
                if now > expire_date:
                    to_remove.append(item_id)
        
        for item_id in to_remove:
            del self._knowledge_cache[item_id]
            removed += 1
        
        if removed > 0:
            self._save_knowledge_index()
        
        return removed
    
    def _save_knowledge_index(self):
        """保存知识索引"""
        file = self.knowledge_dir / "knowledge_index.json"
        try:
            data = [asdict(v) for v in self._knowledge_cache.values()]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------
    
    def get_stats(self) -> Dict[str, Any]:
        """获取学习引擎统计信息"""
        return {
            "knowledge_items": len(self._knowledge_cache),
            "skills_learned": len(self._skills_cache),
            "plugins_discovered": len(self._plugins_cache),
            "learning_records": len(self._learning_records),
            "categories": self._get_category_breakdown(),
        }
    
    def _get_category_breakdown(self) -> Dict[str, int]:
        """按类别统计知识"""
        breakdown = {}
        for item in self._knowledge_cache.values():
            cat = item.category
            breakdown[cat] = breakdown.get(cat, 0) + 1
        return breakdown
    
    def get_recent_learning(self, limit: int = 10) -> List[Dict]:
        """获取最近的学习记录"""
        return [asdict(r) for r in self._learning_records[-limit:]]


    # ------------------------------------------------------------------
    # Phase 2 增强 — 事件总线接入
    # ------------------------------------------------------------------

    def set_event_bus(self, bus) -> None:
        """注入事件总线"""
        self._event_bus = bus
        if self._event_bus:
            self._event_bus.emit("learning", "bus_attached", {
                "knowledge_items": len(self._knowledge_cache),
                "skills_learned": len(self._skills_cache),
                "plugins_discovered": len(self._plugins_cache),
            })

    def _emit(self, kind: str, payload: dict) -> None:
        """便捷事件发布"""
        if self._event_bus:
            self._event_bus.emit("learning", kind, payload)
