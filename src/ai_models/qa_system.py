"""
智能问答系统
基于RAG（检索增强生成）架构，结合知识图谱生成解释性答案
"""

import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json
import re

import openai
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import Document
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from ..core.config import config
from ..knowledge_graph.graph_manager import graph_manager
from ..utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeRetriever:
    """知识检索器"""
    
    def __init__(self):
        self.embedding_model = SentenceTransformer(config.ai_model.sentence_transformer_model)
        self.qdrant_client = QdrantClient(host="localhost", port=6333)
        self.collection_name = "intelligence_knowledge"
        
        # 初始化向量数据库
        self.init_vector_store()
    
    def init_vector_store(self):
        """初始化向量存储"""
        try:
            # 检查集合是否存在
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                # 创建新集合
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=384,  # sentence-transformer向量维度
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"创建向量集合: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"向量存储初始化失败: {str(e)}")
    
    async def add_documents(self, documents: List[Document]):
        """添加文档到向量存储"""
        try:
            # 生成嵌入向量
            texts = [doc.page_content for doc in documents]
            embeddings = self.embedding_model.encode(texts).tolist()
            
            # 准备数据点
            points = []
            for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
                points.append({
                    "id": i,
                    "vector": embedding,
                    "payload": {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "timestamp": datetime.now().isoformat()
                    }
                })
            
            # 批量插入
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"添加 {len(documents)} 个文档到向量存储")
            
        except Exception as e:
            logger.error(f"文档添加失败: {str(e)}")
    
    async def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相似文档"""
        try:
            # 生成查询向量
            query_vector = self.embedding_model.encode([query])[0].tolist()
            
            # 搜索相似向量
            search_result = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True
            )
            
            # 转换结果格式
            results = []
            for hit in search_result:
                results.append({
                    "content": hit.payload["content"],
                    "metadata": hit.payload["metadata"],
                    "score": hit.score,
                    "timestamp": hit.payload["timestamp"]
                })
            
            return results
            
        except Exception as e:
            logger.error(f"相似文档搜索失败: {str(e)}")
            return []


class GraphKnowledgeExtractor:
    """图谱知识提取器"""
    
    def __init__(self):
        self.graph_manager = graph_manager
    
    async def extract_relevant_entities(self, query: str) -> List[Dict[str, Any]]:
        """提取查询相关的实体"""
        try:
            # 使用NLP模型提取查询中的实体
            from ..data_collection.data_parser import NLPProcessor
            nlp_processor = NLPProcessor()
            entities = nlp_processor.extract_entities(query)
            
            # 从知识图谱中查找相关节点
            relevant_nodes = []
            for entity in entities:
                nodes = await self.graph_manager.search_nodes_by_name(entity['text'])
                relevant_nodes.extend(nodes)
            
            # 转换为标准格式
            entity_info = []
            for node in relevant_nodes:
                entity_info.append({
                    "id": node.id,
                    "name": node.properties.get('name', ''),
                    "type": node.type,
                    "properties": node.properties,
                    "confidence": node.confidence
                })
            
            return entity_info
            
        except Exception as e:
            logger.error(f"实体提取失败: {str(e)}")
            return []
    
    async def get_entity_relations(self, entity_id: str) -> List[Dict[str, Any]]:
        """获取实体的关系信息"""
        try:
            query = """
            MATCH (e:Entity {id: $entity_id})-[r:RELATES_TO]-(other:Entity)
            RETURN r, other
            ORDER BY r.strength DESC
            LIMIT 10
            """
            
            relations = []
            with self.graph_manager.neo4j_driver.session() as session:
                result = session.run(query, {'entity_id': entity_id})
                
                for record in result:
                    relation = record['r']
                    other_entity = record['other']
                    
                    relations.append({
                        "relation_type": relation['type'],
                        "strength": relation['strength'],
                        "risk_level": relation['risk_level'],
                        "target_entity": {
                            "id": other_entity['id'],
                            "name": other_entity.get('name', ''),
                            "type": other_entity['type']
                        }
                    })
            
            return relations
            
        except Exception as e:
            logger.error(f"关系查询失败: {str(e)}")
            return []


class AnswerGenerator:
    """答案生成器"""
    
    def __init__(self):
        # 配置OpenAI客户端
        openai.api_key = config.ai_model.openai_api_key
        if config.ai_model.openai_base_url != "https://api.openai.com/v1":
            openai.api_base = config.ai_model.openai_base_url
        
        self.chat_model = config.ai_model.chat_model
    
    async def generate_answer(self, 
                            query: str, 
                            context_docs: List[Dict[str, Any]], 
                            entity_info: List[Dict[str, Any]],
                            confidence_threshold: float = 0.9) -> Dict[str, Any]:
        """生成答案"""
        try:
            # 构建上下文
            context = self.build_context(context_docs, entity_info)
            
            # 构建提示词
            prompt = self.build_prompt(query, context)
            
            # 调用大模型生成答案
            response = await openai.ChatCompletion.acreate(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": "你是一个专业的AI情报分析助手，专门分析电池和储能行业的商业情报。请基于提供的知识图谱和文档信息，给出准确、详细的分析回答。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            answer_text = response.choices[0].message.content
            
            # 计算置信度
            confidence = self.calculate_confidence(answer_text, context_docs, entity_info)
            
            # 提取引用来源
            sources = self.extract_sources(context_docs, entity_info)
            
            return {
                "answer": answer_text,
                "confidence": confidence,
                "sources": sources,
                "entities": entity_info,
                "meets_threshold": confidence >= confidence_threshold,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"答案生成失败: {str(e)}")
            return {
                "answer": "抱歉，当前无法生成回答，请稍后重试。",
                "confidence": 0.0,
                "sources": [],
                "entities": [],
                "meets_threshold": False,
                "timestamp": datetime.now().isoformat()
            }
    
    def build_context(self, context_docs: List[Dict[str, Any]], entity_info: List[Dict[str, Any]]) -> str:
        """构建上下文信息"""
        context_parts = []
        
        # 添加文档上下文
        if context_docs:
            context_parts.append("=== 相关文档信息 ===")
            for i, doc in enumerate(context_docs[:3]):  # 只取前3个最相关的文档
                context_parts.append(f"文档 {i+1}: {doc['content'][:500]}...")
                if doc['metadata']:
                    context_parts.append(f"来源: {doc['metadata'].get('source_url', '未知')}")
        
        # 添加实体信息
        if entity_info:
            context_parts.append("\n=== 相关实体信息 ===")
            for entity in entity_info[:5]:  # 只取前5个实体
                context_parts.append(f"实体: {entity['name']} (类型: {entity['type']})")
                if entity['properties']:
                    key_props = {k: v for k, v in entity['properties'].items() 
                               if k in ['industry', 'risk_level', 'technology_category']}
                    if key_props:
                        context_parts.append(f"属性: {json.dumps(key_props, ensure_ascii=False)}")
        
        return "\n".join(context_parts)
    
    def build_prompt(self, query: str, context: str) -> str:
        """构建提示词"""
        prompt_template = """
基于以下知识图谱和文档信息，请回答用户的问题。

{context}

用户问题: {query}

请提供详细、准确的回答，并在回答中：
1. 引用具体的数据和事实
2. 分析相关的风险和机会
3. 提供可行的建议
4. 标注信息的可信度

回答格式：
【核心回答】
（主要答案内容）

【详细分析】
（基于知识图谱的深度分析）

【风险提示】
（相关风险提醒）

【建议】
（具体建议）

【信息来源】
（引用的主要来源）
"""
        
        return prompt_template.format(context=context, query=query)
    
    def calculate_confidence(self, answer: str, context_docs: List[Dict[str, Any]], entity_info: List[Dict[str, Any]]) -> float:
        """计算答案置信度"""
        confidence_factors = []
        
        # 基于上下文文档的置信度
        if context_docs:
            avg_doc_score = sum(doc['score'] for doc in context_docs) / len(context_docs)
            confidence_factors.append(avg_doc_score * 0.4)
        
        # 基于实体信息的置信度
        if entity_info:
            avg_entity_confidence = sum(entity['confidence'] for entity in entity_info) / len(entity_info)
            confidence_factors.append(avg_entity_confidence * 0.3)
        
        # 基于答案长度和结构的置信度
        answer_quality = min(1.0, len(answer) / 500)  # 归一化答案长度
        if "【" in answer and "】" in answer:  # 检查是否有结构化格式
            answer_quality += 0.2
        confidence_factors.append(answer_quality * 0.3)
        
        # 综合置信度
        if confidence_factors:
            return min(1.0, sum(confidence_factors))
        else:
            return 0.5
    
    def extract_sources(self, context_docs: List[Dict[str, Any]], entity_info: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """提取引用来源"""
        sources = []
        
        # 从文档中提取来源
        for doc in context_docs:
            if doc['metadata'] and doc['metadata'].get('source_url'):
                sources.append({
                    "type": "document",
                    "url": doc['metadata']['source_url'],
                    "title": doc['metadata'].get('title', '未知标题'),
                    "score": doc['score']
                })
        
        # 从实体中提取来源
        for entity in entity_info:
            if entity['properties'] and entity['properties'].get('sources'):
                for source_url in entity['properties']['sources'][:2]:  # 只取前2个来源
                    sources.append({
                        "type": "entity",
                        "url": source_url,
                        "entity_name": entity['name'],
                        "confidence": entity['confidence']
                    })
        
        # 去重并排序
        unique_sources = []
        seen_urls = set()
        for source in sources:
            if source['url'] not in seen_urls:
                unique_sources.append(source)
                seen_urls.add(source['url'])
        
        return sorted(unique_sources, key=lambda x: x.get('score', x.get('confidence', 0)), reverse=True)[:5]


class IntelligentQASystem:
    """智能问答系统主类"""
    
    def __init__(self):
        self.knowledge_retriever = KnowledgeRetriever()
        self.graph_extractor = GraphKnowledgeExtractor()
        self.answer_generator = AnswerGenerator()
        
        # 查询历史
        self.query_history: List[Dict[str, Any]] = []
    
    async def answer_question(self, query: str, confidence_threshold: float = 0.9) -> Dict[str, Any]:
        """回答问题"""
        start_time = datetime.now()
        
        try:
            logger.info(f"处理问题: {query}")
            
            # 1. 检索相关文档
            context_docs = await self.knowledge_retriever.search_similar(query, top_k=10)
            
            # 2. 提取相关实体
            entity_info = await self.graph_extractor.extract_relevant_entities(query)
            
            # 3. 获取实体关系信息
            for entity in entity_info:
                entity['relations'] = await self.graph_extractor.get_entity_relations(entity['id'])
            
            # 4. 生成答案
            result = await self.answer_generator.generate_answer(
                query, context_docs, entity_info, confidence_threshold
            )
            
            # 5. 记录查询历史
            processing_time = (datetime.now() - start_time).total_seconds()
            query_record = {
                "query": query,
                "result": result,
                "processing_time": processing_time,
                "timestamp": start_time.isoformat()
            }
            self.query_history.append(query_record)
            
            # 6. 如果置信度不足，提供改进建议
            if not result['meets_threshold']:
                result['improvement_suggestions'] = self.get_improvement_suggestions(query, result)
            
            logger.info(f"问题处理完成，置信度: {result['confidence']:.2f}, 用时: {processing_time:.2f}秒")
            
            return result
            
        except Exception as e:
            logger.error(f"问题处理失败: {str(e)}")
            return {
                "answer": "抱歉，问题处理过程中发生错误，请稍后重试。",
                "confidence": 0.0,
                "sources": [],
                "entities": [],
                "meets_threshold": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_improvement_suggestions(self, query: str, result: Dict[str, Any]) -> List[str]:
        """获取改进建议"""
        suggestions = []
        
        if result['confidence'] < 0.5:
            suggestions.append("建议重新表述问题，使用更具体的行业术语")
        
        if not result['entities']:
            suggestions.append("建议在问题中包含具体的公司名称、产品或技术名称")
        
        if not result['sources']:
            suggestions.append("相关信息可能不足，建议补充相关数据源")
        
        if len(result['answer']) < 100:
            suggestions.append("答案信息有限，建议提供更多背景信息")
        
        return suggestions
    
    async def get_predefined_answers(self) -> Dict[str, Any]:
        """获取预定义问题的答案示例"""
        predefined_qa = {
            "欧盟2025年电池碳足迹门槛": {
                "question": "欧盟2025年电池碳足迹门槛是什么？",
                "answer": "根据欧盟电池新规，从2025年开始，在欧盟市场销售的电池需要满足特定的碳足迹要求..."
            },
            "印尼镍矿出口限制影响": {
                "question": "印尼镍矿出口限制对高镍三元电池产能有什么影响？",
                "answer": "印尼是全球最大的镍矿供应国，其出口限制政策将直接影响..."
            }
        }
        
        return predefined_qa
    
    async def batch_process_questions(self, questions: List[str]) -> List[Dict[str, Any]]:
        """批量处理问题"""
        results = []
        
        # 并发处理多个问题
        tasks = [self.answer_question(q) for q in questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "query": questions[i],
                    "answer": f"处理失败: {str(result)}",
                    "confidence": 0.0,
                    "error": True
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """获取查询统计信息"""
        if not self.query_history:
            return {"total_queries": 0}
        
        total_queries = len(self.query_history)
        avg_confidence = sum(q['result']['confidence'] for q in self.query_history) / total_queries
        avg_processing_time = sum(q['processing_time'] for q in self.query_history) / total_queries
        
        high_confidence_count = sum(1 for q in self.query_history if q['result']['confidence'] >= 0.9)
        
        return {
            "total_queries": total_queries,
            "average_confidence": avg_confidence,
            "average_processing_time": avg_processing_time,
            "high_confidence_rate": high_confidence_count / total_queries,
            "recent_queries": [q['query'] for q in self.query_history[-5:]]
        }


# 全局问答系统实例
qa_system = IntelligentQASystem()