"""
知识图谱管理器
支持动态更新机制，实时响应外部事件并自动触发图谱重构
"""

import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

from neo4j import GraphDatabase
import networkx as nx
from sentence_transformers import SentenceTransformer

from ..core.config import config
from ..data_collection.data_parser import ParsedData, EntityRelation
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GraphNode:
    """知识图谱节点"""
    id: str
    type: str  # 企业实体、技术路线、法规条款、材料供应商、风险事件
    properties: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    confidence: float = 1.0


@dataclass
class GraphRelation:
    """知识图谱关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any]
    strength: float  # 关联强度
    risk_level: str  # 风险等级
    created_at: datetime
    updated_at: datetime


@dataclass
class GraphEvent:
    """图谱事件"""
    event_type: str  # create, update, delete
    node_id: Optional[str] = None
    relation_id: Optional[str] = None
    trigger: str = ""  # 触发源
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class GraphManager:
    """知识图谱管理器"""
    
    def __init__(self):
        self.neo4j_driver = None
        self.networkx_graph = nx.MultiDiGraph()
        self.sentence_model = SentenceTransformer(config.ai_model.sentence_transformer_model)
        
        # 事件监听器
        self.event_listeners: List[callable] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        
        # 节点和关系缓存
        self.nodes_cache: Dict[str, GraphNode] = {}
        self.relations_cache: Dict[str, GraphRelation] = {}
        
        # 初始化连接
        self.init_connections()
    
    def init_connections(self):
        """初始化数据库连接"""
        try:
            self.neo4j_driver = GraphDatabase.driver(
                config.database.neo4j_uri,
                auth=(config.database.neo4j_user, config.database.neo4j_password)
            )
            
            # 测试连接
            with self.neo4j_driver.session() as session:
                session.run("RETURN 1")
            
            logger.info("Neo4j连接成功")
            
            # 创建索引
            self.create_indexes()
            
        except Exception as e:
            logger.error(f"Neo4j连接失败: {str(e)}")
            raise
    
    def create_indexes(self):
        """创建必要的索引"""
        indexes = [
            "CREATE INDEX node_id_index IF NOT EXISTS FOR (n:Entity) ON (n.id)",
            "CREATE INDEX node_type_index IF NOT EXISTS FOR (n:Entity) ON (n.type)",
            "CREATE INDEX relation_type_index IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type)",
            "CREATE INDEX updated_at_index IF NOT EXISTS FOR (n:Entity) ON (n.updated_at)"
        ]
        
        try:
            with self.neo4j_driver.session() as session:
                for index_query in indexes:
                    session.run(index_query)
            logger.info("索引创建完成")
        except Exception as e:
            logger.error(f"索引创建失败: {str(e)}")
    
    async def add_parsed_data(self, parsed_data: ParsedData):
        """添加解析后的数据到知识图谱"""
        try:
            # 创建或更新实体节点
            entity_nodes = await self.process_entities(parsed_data.entities, parsed_data)
            
            # 创建或更新关系
            await self.process_relations(parsed_data.relations, entity_nodes)
            
            # 触发图谱更新事件
            await self.trigger_event(GraphEvent(
                event_type="batch_update",
                trigger=f"parsed_data_{parsed_data.source_type}",
                timestamp=datetime.now()
            ))
            
            logger.info(f"知识图谱更新完成: {len(entity_nodes)} 个实体, {len(parsed_data.relations)} 个关系")
            
        except Exception as e:
            logger.error(f"知识图谱更新失败: {str(e)}")
    
    async def process_entities(self, entities: List[Dict[str, Any]], parsed_data: ParsedData) -> List[GraphNode]:
        """处理实体数据"""
        graph_nodes = []
        
        for entity in entities:
            # 生成唯一ID
            entity_id = self.generate_entity_id(entity['text'], entity['label'])
            
            # 检查是否已存在
            existing_node = await self.get_node(entity_id)
            
            if existing_node:
                # 更新现有节点
                await self.update_node(
                    entity_id,
                    {
                        'confidence': max(existing_node.confidence, entity['confidence']),
                        'sources': existing_node.properties.get('sources', []) + [parsed_data.source_url],
                        'last_seen': datetime.now().isoformat()
                    }
                )
                graph_nodes.append(existing_node)
            else:
                # 创建新节点
                node_properties = {
                    'name': entity['text'],
                    'label': entity['label'],
                    'confidence': entity['confidence'],
                    'sources': [parsed_data.source_url],
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat()
                }
                
                # 根据实体类型添加特定属性
                node_properties.update(self.get_entity_specific_properties(entity, parsed_data))
                
                graph_node = await self.create_node(
                    entity_id,
                    self.map_entity_type(entity['label']),
                    node_properties
                )
                graph_nodes.append(graph_node)
        
        return graph_nodes
    
    def generate_entity_id(self, text: str, label: str) -> str:
        """生成实体唯一ID"""
        # 使用文本和标签生成稳定的ID
        import hashlib
        content = f"{text.lower()}_{label}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def map_entity_type(self, label: str) -> str:
        """映射实体类型到图谱节点类型"""
        type_mapping = {
            'ORG': 'Company',
            'PERSON': 'Person',
            'GPE': 'Location',
            'MONEY': 'FinancialInfo',
            'DATE': 'TimeInfo',
            'PRODUCT': 'Technology',
            'LAW': 'Regulation'
        }
        return type_mapping.get(label, 'Entity')
    
    def get_entity_specific_properties(self, entity: Dict[str, Any], parsed_data: ParsedData) -> Dict[str, Any]:
        """根据实体类型获取特定属性"""
        properties = {}
        
        entity_type = self.map_entity_type(entity['label'])
        
        if entity_type == 'Company':
            # 企业实体的特定属性
            properties.update({
                'industry': self.extract_industry(parsed_data.content),
                'business_type': self.extract_business_type(parsed_data.content, entity['text']),
                'risk_level': 'unknown'
            })
        
        elif entity_type == 'Technology':
            # 技术实体的特定属性
            properties.update({
                'technology_category': self.extract_tech_category(entity['text']),
                'maturity_level': 'unknown',
                'innovation_index': 0.5
            })
        
        elif entity_type == 'Regulation':
            # 法规实体的特定属性
            properties.update({
                'jurisdiction': self.extract_jurisdiction(parsed_data.content),
                'regulation_type': self.extract_regulation_type(parsed_data.content),
                'enforcement_date': self.extract_enforcement_date(parsed_data.content)
            })
        
        return properties
    
    def extract_industry(self, content: str) -> str:
        """从内容中提取行业信息"""
        industry_keywords = {
            '储能': 'energy_storage',
            '电池': 'battery',
            '新能源': 'renewable_energy',
            '锂电': 'lithium_battery',
            '光伏': 'solar',
            '风电': 'wind_power'
        }
        
        for keyword, industry in industry_keywords.items():
            if keyword in content:
                return industry
        
        return 'unknown'
    
    def extract_tech_category(self, tech_name: str) -> str:
        """提取技术分类"""
        tech_categories = {
            '锂离子': 'lithium_ion',
            '钠离子': 'sodium_ion',
            '固态': 'solid_state',
            '磷酸铁锂': 'lfp',
            '三元': 'ncm'
        }
        
        for keyword, category in tech_categories.items():
            if keyword in tech_name:
                return category
        
        return 'unknown'
    
    async def process_relations(self, relations: List[EntityRelation], entity_nodes: List[GraphNode]):
        """处理关系数据"""
        for relation in relations:
            # 查找源和目标节点
            source_node = next((n for n in entity_nodes if relation.subject in n.properties.get('name', '')), None)
            target_node = next((n for n in entity_nodes if relation.object in n.properties.get('name', '')), None)
            
            if source_node and target_node:
                relation_id = f"{source_node.id}_{relation.predicate}_{target_node.id}"
                
                # 计算关系强度和风险等级
                strength = self.calculate_relation_strength(relation, source_node, target_node)
                risk_level = self.assess_risk_level(relation, source_node, target_node)
                
                await self.create_or_update_relation(
                    relation_id,
                    source_node.id,
                    target_node.id,
                    relation.predicate,
                    {
                        'confidence': relation.confidence,
                        'source': relation.source,
                        'created_from': relation.timestamp.isoformat()
                    },
                    strength,
                    risk_level
                )
    
    def calculate_relation_strength(self, relation: EntityRelation, source: GraphNode, target: GraphNode) -> float:
        """计算关系强度"""
        # 基础强度基于置信度
        base_strength = relation.confidence
        
        # 根据关系类型调整
        relation_weights = {
            '供应': 0.9,
            '合作': 0.8,
            '竞争': 0.7,
            '投资': 0.85,
            '技术': 0.75,
            '监管': 0.95
        }
        
        type_weight = relation_weights.get(relation.predicate, 0.5)
        
        # 考虑节点的可信度
        node_reliability = (source.confidence + target.confidence) / 2
        
        return min(1.0, base_strength * type_weight * node_reliability)
    
    def assess_risk_level(self, relation: EntityRelation, source: GraphNode, target: GraphNode) -> str:
        """评估关系的风险等级"""
        # 根据关系类型和节点特征评估风险
        high_risk_relations = ['竞争', '监管']
        medium_risk_relations = ['供应', '投资']
        
        if relation.predicate in high_risk_relations:
            return 'high'
        elif relation.predicate in medium_risk_relations:
            return 'medium'
        else:
            return 'low'
    
    async def create_node(self, node_id: str, node_type: str, properties: Dict[str, Any]) -> GraphNode:
        """创建新节点"""
        graph_node = GraphNode(
            id=node_id,
            type=node_type,
            properties=properties,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            confidence=properties.get('confidence', 1.0)
        )
        
        # 保存到Neo4j
        await self.save_node_to_neo4j(graph_node)
        
        # 更新缓存
        self.nodes_cache[node_id] = graph_node
        
        # 更新NetworkX图
        self.networkx_graph.add_node(node_id, **properties, type=node_type)
        
        # 触发事件
        await self.trigger_event(GraphEvent(
            event_type="create",
            node_id=node_id,
            trigger="data_ingestion"
        ))
        
        return graph_node
    
    async def save_node_to_neo4j(self, node: GraphNode):
        """保存节点到Neo4j"""
        query = """
        MERGE (n:Entity {id: $id})
        SET n.type = $type,
            n.created_at = $created_at,
            n.updated_at = $updated_at,
            n.confidence = $confidence
        """
        
        # 添加动态属性
        for key, value in node.properties.items():
            query += f", n.{key} = ${key}"
        
        parameters = {
            'id': node.id,
            'type': node.type,
            'created_at': node.created_at.isoformat(),
            'updated_at': node.updated_at.isoformat(),
            'confidence': node.confidence,
            **node.properties
        }
        
        try:
            with self.neo4j_driver.session() as session:
                session.run(query, parameters)
        except Exception as e:
            logger.error(f"保存节点到Neo4j失败: {str(e)}")
    
    async def create_or_update_relation(self, relation_id: str, source_id: str, target_id: str, 
                                      relation_type: str, properties: Dict[str, Any], 
                                      strength: float, risk_level: str):
        """创建或更新关系"""
        existing_relation = self.relations_cache.get(relation_id)
        
        if existing_relation:
            # 更新现有关系
            existing_relation.strength = max(existing_relation.strength, strength)
            existing_relation.updated_at = datetime.now()
            existing_relation.properties.update(properties)
        else:
            # 创建新关系
            graph_relation = GraphRelation(
                id=relation_id,
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                properties=properties,
                strength=strength,
                risk_level=risk_level,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            self.relations_cache[relation_id] = graph_relation
            
            # 保存到Neo4j
            await self.save_relation_to_neo4j(graph_relation)
            
            # 更新NetworkX图
            self.networkx_graph.add_edge(
                source_id, target_id,
                key=relation_id,
                type=relation_type,
                strength=strength,
                risk_level=risk_level,
                **properties
            )
    
    async def save_relation_to_neo4j(self, relation: GraphRelation):
        """保存关系到Neo4j"""
        query = """
        MATCH (source:Entity {id: $source_id}), (target:Entity {id: $target_id})
        MERGE (source)-[r:RELATES_TO {id: $relation_id}]->(target)
        SET r.type = $relation_type,
            r.strength = $strength,
            r.risk_level = $risk_level,
            r.created_at = $created_at,
            r.updated_at = $updated_at
        """
        
        # 添加动态属性
        for key, value in relation.properties.items():
            query += f", r.{key} = ${key}"
        
        parameters = {
            'source_id': relation.source_id,
            'target_id': relation.target_id,
            'relation_id': relation.id,
            'relation_type': relation.relation_type,
            'strength': relation.strength,
            'risk_level': relation.risk_level,
            'created_at': relation.created_at.isoformat(),
            'updated_at': relation.updated_at.isoformat(),
            **relation.properties
        }
        
        try:
            with self.neo4j_driver.session() as session:
                session.run(query, parameters)
        except Exception as e:
            logger.error(f"保存关系到Neo4j失败: {str(e)}")
    
    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点"""
        # 先检查缓存
        if node_id in self.nodes_cache:
            return self.nodes_cache[node_id]
        
        # 从Neo4j查询
        query = "MATCH (n:Entity {id: $id}) RETURN n"
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, {'id': node_id})
                record = result.single()
                
                if record:
                    node_data = record['n']
                    graph_node = GraphNode(
                        id=node_data['id'],
                        type=node_data['type'],
                        properties=dict(node_data),
                        created_at=datetime.fromisoformat(node_data['created_at']),
                        updated_at=datetime.fromisoformat(node_data['updated_at']),
                        confidence=node_data.get('confidence', 1.0)
                    )
                    
                    # 更新缓存
                    self.nodes_cache[node_id] = graph_node
                    return graph_node
        
        except Exception as e:
            logger.error(f"获取节点失败: {str(e)}")
        
        return None
    
    async def update_node(self, node_id: str, updates: Dict[str, Any]):
        """更新节点"""
        node = await self.get_node(node_id)
        if not node:
            return
        
        # 更新属性
        node.properties.update(updates)
        node.updated_at = datetime.now()
        
        # 保存到Neo4j
        await self.save_node_to_neo4j(node)
        
        # 触发更新事件
        await self.trigger_event(GraphEvent(
            event_type="update",
            node_id=node_id,
            trigger="data_update"
        ))
    
    async def trigger_event(self, event: GraphEvent):
        """触发图谱事件"""
        await self.event_queue.put(event)
        
        # 通知事件监听器
        for listener in self.event_listeners:
            try:
                await listener(event)
            except Exception as e:
                logger.error(f"事件监听器执行失败: {str(e)}")
    
    def add_event_listener(self, listener: callable):
        """添加事件监听器"""
        self.event_listeners.append(listener)
    
    async def handle_external_event(self, event_data: Dict[str, Any]):
        """处理外部事件（如制裁清单更新）"""
        event_type = event_data.get('type')
        
        if event_type == 'sanctions_update':
            # 处理制裁清单更新
            await self.process_sanctions_update(event_data)
        
        elif event_type == 'regulation_change':
            # 处理法规变更
            await self.process_regulation_change(event_data)
        
        elif event_type == 'market_disruption':
            # 处理市场中断事件
            await self.process_market_disruption(event_data)
    
    async def process_sanctions_update(self, event_data: Dict[str, Any]):
        """处理制裁清单更新"""
        sanctioned_entities = event_data.get('entities', [])
        
        for entity_name in sanctioned_entities:
            # 查找相关节点
            matching_nodes = await self.search_nodes_by_name(entity_name)
            
            for node in matching_nodes:
                # 更新风险等级
                await self.update_node(node.id, {
                    'risk_level': 'high',
                    'sanctions_status': 'sanctioned',
                    'sanctions_updated': datetime.now().isoformat()
                })
                
                # 更新相关关系的风险等级
                await self.update_related_relations_risk(node.id, 'high')
        
        logger.info(f"制裁清单更新完成，影响 {len(sanctioned_entities)} 个实体")
    
    async def search_nodes_by_name(self, name: str) -> List[GraphNode]:
        """根据名称搜索节点"""
        query = """
        MATCH (n:Entity)
        WHERE n.name CONTAINS $name OR $name CONTAINS n.name
        RETURN n
        """
        
        nodes = []
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, {'name': name})
                
                for record in result:
                    node_data = record['n']
                    graph_node = GraphNode(
                        id=node_data['id'],
                        type=node_data['type'],
                        properties=dict(node_data),
                        created_at=datetime.fromisoformat(node_data['created_at']),
                        updated_at=datetime.fromisoformat(node_data['updated_at']),
                        confidence=node_data.get('confidence', 1.0)
                    )
                    nodes.append(graph_node)
        
        except Exception as e:
            logger.error(f"搜索节点失败: {str(e)}")
        
        return nodes
    
    async def update_related_relations_risk(self, node_id: str, risk_level: str):
        """更新相关关系的风险等级"""
        query = """
        MATCH (n:Entity {id: $node_id})-[r:RELATES_TO]-()
        SET r.risk_level = $risk_level, r.risk_updated = $timestamp
        RETURN count(r) as updated_count
        """
        
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, {
                    'node_id': node_id,
                    'risk_level': risk_level,
                    'timestamp': datetime.now().isoformat()
                })
                
                record = result.single()
                if record:
                    logger.info(f"更新了 {record['updated_count']} 个关系的风险等级")
        
        except Exception as e:
            logger.error(f"更新关系风险等级失败: {str(e)}")
    
    async def start_event_processor(self):
        """启动事件处理器"""
        logger.info("启动知识图谱事件处理器")
        
        while True:
            try:
                # 处理事件队列
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                await self.process_graph_event(event)
                
            except asyncio.TimeoutError:
                # 定期执行图谱维护任务
                await self.periodic_maintenance()
            
            except Exception as e:
                logger.error(f"事件处理失败: {str(e)}")
    
    async def process_graph_event(self, event: GraphEvent):
        """处理图谱事件"""
        logger.info(f"处理图谱事件: {event.event_type} - {event.trigger}")
        
        if event.event_type == "batch_update":
            # 批量更新后的优化
            await self.optimize_graph_structure()
        
        elif event.event_type == "create":
            # 新节点创建后的关联分析
            if event.node_id:
                await self.analyze_new_node_connections(event.node_id)
    
    async def periodic_maintenance(self):
        """定期维护任务"""
        # 清理过期的缓存
        current_time = datetime.now()
        
        # 每小时执行一次图谱压缩
        if current_time.minute == 0:
            await self.compress_graph()
        
        # 每天执行一次性能优化
        if current_time.hour == 2 and current_time.minute == 0:
            await self.optimize_graph_performance()
    
    async def compress_graph(self):
        """压缩图谱，合并相似节点"""
        logger.info("开始图谱压缩...")
        
        # 查找相似节点
        similar_nodes = await self.find_similar_nodes()
        
        for node_group in similar_nodes:
            if len(node_group) > 1:
                # 合并相似节点
                await self.merge_nodes(node_group)
        
        logger.info("图谱压缩完成")
    
    async def find_similar_nodes(self) -> List[List[GraphNode]]:
        """查找相似节点"""
        # 使用语义相似度计算
        # 这里简化实现，实际应该使用更复杂的相似度算法
        return []
    
    async def merge_nodes(self, nodes: List[GraphNode]):
        """合并相似节点"""
        if len(nodes) < 2:
            return
        
        # 选择置信度最高的节点作为主节点
        primary_node = max(nodes, key=lambda x: x.confidence)
        secondary_nodes = [n for n in nodes if n.id != primary_node.id]
        
        # 合并属性
        for secondary_node in secondary_nodes:
            # 合并sources
            existing_sources = primary_node.properties.get('sources', [])
            new_sources = secondary_node.properties.get('sources', [])
            primary_node.properties['sources'] = list(set(existing_sources + new_sources))
            
            # 更新置信度
            primary_node.confidence = max(primary_node.confidence, secondary_node.confidence)
            
            # 迁移关系
            await self.migrate_node_relations(secondary_node.id, primary_node.id)
            
            # 删除次要节点
            await self.delete_node(secondary_node.id)
    
    async def migrate_node_relations(self, from_node_id: str, to_node_id: str):
        """迁移节点关系"""
        query = """
        MATCH (from:Entity {id: $from_id})-[r:RELATES_TO]-(other:Entity)
        WHERE other.id <> $to_id
        CREATE (to:Entity {id: $to_id})-[new_r:RELATES_TO]-(other)
        SET new_r = r
        DELETE r
        """
        
        try:
            with self.neo4j_driver.session() as session:
                session.run(query, {'from_id': from_node_id, 'to_id': to_node_id})
        except Exception as e:
            logger.error(f"关系迁移失败: {str(e)}")
    
    async def delete_node(self, node_id: str):
        """删除节点"""
        query = "MATCH (n:Entity {id: $id}) DETACH DELETE n"
        
        try:
            with self.neo4j_driver.session() as session:
                session.run(query, {'id': node_id})
            
            # 从缓存中删除
            self.nodes_cache.pop(node_id, None)
            
            # 从NetworkX图中删除
            if self.networkx_graph.has_node(node_id):
                self.networkx_graph.remove_node(node_id)
        
        except Exception as e:
            logger.error(f"删除节点失败: {str(e)}")
    
    def close(self):
        """关闭连接"""
        if self.neo4j_driver:
            self.neo4j_driver.close()


# 全局图谱管理器实例
graph_manager = GraphManager()