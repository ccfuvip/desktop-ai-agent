"""
记忆存储引擎 (Memory Store)
==========================
向量记忆 + 知识图谱 + 经验库

技术栈:
- 向量存储: ChromaDB (持久化)
- 知识图谱: NetworkX
- 经验日志: JSON文件

数据结构:
1. 短期记忆: 当前对话上下文
2. 长期记忆: ChromaDB向量存储
3. 语义记忆: 事实性知识 (模型、工具、技能)
4. 程序记忆: 操作流程和最佳实践
5. 经验记忆: 成功案例和失败教训

作者: Desktop AI Agent
版本: 1.0.0
"""

import json
import time
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """单条记忆"""
    id: str = ""
    content: str = ""
    category: str = "general"  # general, task, skill, fact, experience
    tags: List[str] = field(default_factory=list)
    embedding_hint: str = ""  # 用于生成embeddings的提示
    created_at: float = 0.0
    updated_at: float = 0.0
    access_count: int = 0
    importance: float = 0.5  # 0-1, 重要性评分
    source: str = "manual"  # manual, auto, learned


class MemoryStore:
    """
    记忆存储系统
    
    三层记忆架构:
    Layer 1: ChromaDB 向量记忆 (语义搜索)
    Layer 2: 知识图谱 (关系型记忆)
    Layer 3: 经验日志 (时间线记忆)
    
    使用示例:
        store = MemoryStore()
        
        # 存储
        store.add("用户喜欢深色主题", category="fact", tags=["preference"])
        
        # 搜索
        results = store.search("用户的界面偏好", top_k=3)
        
        # 获取相关经验
        experiences = store.get_experiences("chrome浏览器")
    """
    
    def __init__(self, project_dir=None, data_dir: str = None):
        if data_dir is None and project_dir is not None:
            data_dir = str(Path(project_dir) / "data" / "memory")
        if data_dir is None:
            data_dir = "./data/memory"
        self.project_dir = Path(project_dir) if project_dir is not None else None
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # ChromaDB 向量存储
        self._chroma_db = None
        self._chroma_collection = None
        self._init_chroma()
        
        # 内存中的短期记忆
        self.short_term_memories: List[Dict] = []
        self.max_short_term = 50
        
        # 经验日志
        self.experience_log = self._load_experience_log()
        
        # 统计
        self.stats = {
            "total_entries": 0,
            "search_count": 0,
            "last_search": None,
        }
    
    def _init_chroma(self):
        """初始化ChromaDB"""
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
            self._chroma_db = client
            self._chroma_collection = client.get_or_create_collection(
                name="agent_memories",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("✅ ChromaDB 初始化成功")
        except ImportError:
            logger.warning("⚠️ chromadb 未安装，使用文件存储")
            self._chroma_db = None
        except Exception as e:
            logger.warning(f"⚠️ ChromaDB 初始化失败: {e}，使用文件存储")
            self._chroma_db = None
    
    def add(self, content: str, category: str = "general",
            tags: List[str] = None, importance: float = 0.5,
            source: str = "manual", embedding_hint: str = "") -> str:
        """
        添加记忆
        
        Args:
            content: 记忆内容
            category: 类别 (general/task/skill/fact/experience)
            tags: 标签
            importance: 重要性 (0-1)
            source: 来源 (manual/auto/learned)
            embedding_hint: 嵌入提示
            
        Returns:
            记忆ID
        """
        memory_id = f"mem_{int(time.time()*1000)}_{len(self.short_term_memories)}"
        now = time.time()
        
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            category=category,
            tags=tags or [],
            importance=importance,
            source=source,
            embedding_hint=embedding_hint or content,
            created_at=now,
            updated_at=now,
        )
        
        # 存入短期记忆
        self.short_term_memories.append(asdict(entry))
        if len(self.short_term_memories) > self.max_short_term:
            self.short_term_memories.pop(0)
        
        # 存入ChromaDB
        if self._chroma_db and self._chroma_collection:
            try:
                self._chroma_collection.add(
                    ids=[memory_id],
                    documents=[content],
                    metadatas=[{
                        "category": category,
                        "tags": ",".join(tags or []),
                        "importance": importance,
                        "source": source,
                        "created_at": now,
                    }],
                )
            except Exception as e:
                logger.warning(f"ChromaDB写入失败: {e}")
        
        # 持久化到文件
        self._save_entry(entry)
        
        self.stats["total_entries"] += 1
        return memory_id
    
    def search(self, query: str, top_k: int = 5,
               categories: List[str] = None) -> List[Dict]:
        """
        语义搜索记忆
        
        Args:
            query: 搜索查询
            top_k: 返回数量
            categories: 过滤类别
            
        Returns:
            记忆列表
        """
        self.stats["search_count"] += 1
        self.stats["last_search"] = query
        
        results = []
        
        # ChromaDB搜索
        if self._chroma_db and self._chroma_collection:
            try:
                kwargs = {
                    "query_texts": [query],
                    "n_results": top_k * 2,  # 多取一些用于过滤
                    "include": ["metadatas", "distances"],
                }
                if categories:
                    kwargs["where"] = {
                        "category": {"$in": categories}
                    }
                
                response = self._chroma_collection.query(**kwargs)
                
                if not response.get("documents") or not response["documents"][0]:
                    return []
                
                for i, doc in enumerate(response["documents"][0]):
                    meta = (response["metadatas"][0][i] if response["metadatas"] 
                           else {})
                    distance = (response["distances"][0][i] 
                               if response["distances"] else 0)
                    
                    results.append({
                        "content": doc,
                        "category": meta.get("category", "general"),
                        "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
                        "importance": float(meta.get("importance", 0.5)),
                        "source": meta.get("source", "unknown"),
                        "similarity": round(1 - distance, 4),
                        "created_at": meta.get("created_at"),
                    })
            except Exception as e:
                logger.warning(f"ChromaDB搜索失败: {e}")
        
        # 如果ChromaDB没结果，回退到文件搜索
        if not results:
            results = self._file_search(query, top_k, categories)
        
        # 按重要性和相关性排序
        results.sort(key=lambda x: x.get("similarity", 0) * x.get("importance", 0.5), 
                    reverse=True)
        
        return results[:top_k]
    
    def get_experiences(self, keyword: str = None, 
                        success_only: bool = None) -> List[Dict]:
        """获取经验日志"""
        experiences = self.experience_log
        
        if keyword:
            experiences = [e for e in experiences 
                         if keyword.lower() in json.dumps(e).lower()]
        
        if success_only is not None:
            experiences = [e for e in experiences 
                         if e.get("success") == success_only]
        
        return experiences[-20:]  # 最近20条
    
    def save_experience(self, experience: Dict):
        """保存经验"""
        experience["timestamp"] = datetime.now().isoformat()
        self.experience_log.append(experience)
        
        # 限制日志大小
        if len(self.experience_log) > 1000:
            self.experience_log = self.experience_log[-1000:]
        
        self._save_experience_log()
    
    def get_recent_memories(self, hours: int = 24, 
                           limit: int = 20) -> List[Dict]:
        """获取最近的记忆"""
        cutoff = time.time() - (hours * 3600)
        return [
            m for m in self.short_term_memories
            if m.get("created_at", 0) > cutoff
        ][-limit:]
    
    def clear(self, category: str = None):
        """清空记忆"""
        if category:
            self.short_term_memories = [
                m for m in self.short_term_memories
                if m.get("category") != category
            ]
        else:
            self.short_term_memories.clear()
        
        if self._chroma_collection:
            try:
                self._chroma_collection.delete()
            except Exception:
                pass
    
    def get_stats(self) -> Dict:
        """获取记忆统计"""
        return {
            **self.stats,
            "short_term_count": len(self.short_term_memories),
            "experience_count": len(self.experience_log),
            "categories": self._count_categories(),
        }
    
    # ---- 私有方法 ----
    
    def _save_entry(self, entry: MemoryEntry):
        """持久化单条记忆到文件"""
        file_path = self.data_dir / "entries" / f"{entry.id}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(entry), f, ensure_ascii=False, indent=2)
    
    def _load_entry(self, entry_id: str) -> Optional[Dict]:
        """从文件加载记忆"""
        file_path = self.data_dir / "entries" / f"{entry_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def _file_search(self, query: str, top_k: int, 
                     categories: List[str] = None) -> List[Dict]:
        """文件回退搜索"""
        results = []
        entries_dir = self.data_dir / "entries"
        
        if not entries_dir.exists():
            return results
        
        for file_path in entries_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                
                content = entry.get("content", "")
                if query.lower() in content.lower():
                    results.append({
                        "content": content,
                        "category": entry.get("category", "general"),
                        "tags": entry.get("tags", []),
                        "importance": entry.get("importance", 0.5),
                        "source": entry.get("source", "unknown"),
                        "similarity": 0.8,  # 简单匹配给高分
                        "created_at": entry.get("created_at"),
                    })
            except Exception:
                pass
        
        return results[:top_k]
    
    def _load_experience_log(self) -> List[Dict]:
        """加载经验日志"""
        log_path = self.data_dir / "experiences.json"
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []
    
    def _save_experience_log(self):
        """保存经验日志"""
        log_path = self.data_dir / "experiences.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.experience_log, f, ensure_ascii=False, indent=2)
    
    def _count_categories(self) -> Dict:
        """统计各类别数量"""
        counts = {}
        for m in self.short_term_memories:
            cat = m.get("category", "general")
            counts[cat] = counts.get(cat, 0) + 1
        return counts
