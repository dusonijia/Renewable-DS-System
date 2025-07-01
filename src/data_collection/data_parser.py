"""
数据解析器
使用NLP模型实现语义解析，生成实体-关系三元组
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import pandas as pd
from bs4 import BeautifulSoup

import torch
from transformers import AutoTokenizer, AutoModel, pipeline
from sentence_transformers import SentenceTransformer
import spacy

from ..core.config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EntityRelation:
    """实体关系三元组"""
    subject: str
    predicate: str
    object: str
    confidence: float
    source: str
    timestamp: datetime


@dataclass
class ParsedData:
    """解析后的结构化数据"""
    source_url: str
    source_type: str
    title: str
    content: str
    entities: List[Dict[str, Any]]
    relations: List[EntityRelation]
    metadata: Dict[str, Any]
    timestamp: datetime


class NLPProcessor:
    """NLP处理器"""
    
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"使用设备: {self.device}")
        
        # 初始化模型
        self.init_models()
    
    def init_models(self):
        """初始化NLP模型"""
        try:
            # BERT模型用于实体识别
            self.tokenizer = AutoTokenizer.from_pretrained(config.ai_model.bert_model_name)
            self.bert_model = AutoModel.from_pretrained(config.ai_model.bert_model_name)
            self.bert_model.to(self.device)
            
            # 句子嵌入模型
            self.sentence_model = SentenceTransformer(config.ai_model.sentence_transformer_model)
            
            # 命名实体识别管道
            self.ner_pipeline = pipeline(
                "ner",
                model="ckiplab/bert-base-chinese-ner",
                tokenizer="ckiplab/bert-base-chinese-ner",
                aggregation_strategy="simple"
            )
            
            # 加载spaCy模型（如果可用）
            try:
                self.nlp = spacy.load("zh_core_web_sm")
            except OSError:
                logger.warning("未找到中文spaCy模型，某些功能可能受限")
                self.nlp = None
            
            logger.info("NLP模型初始化完成")
            
        except Exception as e:
            logger.error(f"NLP模型初始化失败: {str(e)}")
            raise
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """提取命名实体"""
        entities = []
        
        try:
            # 使用BERT NER
            ner_results = self.ner_pipeline(text)
            
            for entity in ner_results:
                entities.append({
                    'text': entity['word'],
                    'label': entity['entity_group'],
                    'confidence': entity['score'],
                    'start': entity.get('start', 0),
                    'end': entity.get('end', 0)
                })
            
            # 使用spaCy进行补充识别
            if self.nlp:
                doc = self.nlp(text)
                for ent in doc.ents:
                    entities.append({
                        'text': ent.text,
                        'label': ent.label_,
                        'confidence': 0.8,  # spaCy没有直接提供置信度
                        'start': ent.start_char,
                        'end': ent.end_char
                    })
            
            # 去重并合并相似实体
            entities = self.merge_similar_entities(entities)
            
        except Exception as e:
            logger.error(f"实体提取失败: {str(e)}")
        
        return entities
    
    def merge_similar_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并相似的实体"""
        if not entities:
            return entities
        
        merged = []
        entities = sorted(entities, key=lambda x: x['confidence'], reverse=True)
        
        for entity in entities:
            is_duplicate = False
            for merged_entity in merged:
                # 检查文本相似度
                if (entity['text'].lower() == merged_entity['text'].lower() or
                    entity['text'] in merged_entity['text'] or
                    merged_entity['text'] in entity['text']):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                merged.append(entity)
        
        return merged
    
    def extract_relations(self, text: str, entities: List[Dict[str, Any]]) -> List[EntityRelation]:
        """提取实体间关系"""
        relations = []
        
        try:
            # 简单的关系模式匹配
            relation_patterns = {
                '供应': ['供应', '提供', '供应商', '供货'],
                '合作': ['合作', '合作伙伴', '合资', '联合'],
                '竞争': ['竞争', '对手', '竞品'],
                '投资': ['投资', '融资', '注资', '收购'],
                '生产': ['生产', '制造', '产能', '工厂'],
                '技术': ['技术', '专利', '研发', '创新'],
                '监管': ['监管', '法规', '政策', '标准']
            }
            
            # 提取企业名称
            company_entities = [e for e in entities if e['label'] in ['ORG', 'COMPANY']]
            
            for i, entity1 in enumerate(company_entities):
                for entity2 in company_entities[i+1:]:
                    # 在文本中查找两个实体之间的关系
                    entity1_pos = text.find(entity1['text'])
                    entity2_pos = text.find(entity2['text'])
                    
                    if entity1_pos != -1 and entity2_pos != -1:
                        # 提取两个实体之间的文本
                        start_pos = min(entity1_pos, entity2_pos)
                        end_pos = max(entity1_pos + len(entity1['text']), 
                                    entity2_pos + len(entity2['text']))
                        context = text[start_pos:end_pos]
                        
                        # 匹配关系模式
                        for relation_type, patterns in relation_patterns.items():
                            for pattern in patterns:
                                if pattern in context:
                                    relations.append(EntityRelation(
                                        subject=entity1['text'],
                                        predicate=relation_type,
                                        object=entity2['text'],
                                        confidence=0.7,
                                        source='pattern_matching',
                                        timestamp=datetime.now()
                                    ))
                                    break
            
        except Exception as e:
            logger.error(f"关系提取失败: {str(e)}")
        
        return relations


class DataParser:
    """数据解析器主类"""
    
    def __init__(self):
        self.nlp_processor = NLPProcessor()
        
        # 注册不同类型的解析器
        self.parsers = {
            'government_tender': self.parse_government_tender,
            'patent': self.parse_patent,
            'regulation': self.parse_regulation,
            'supplier': self.parse_supplier_data,
            'market_report': self.parse_market_report
        }
    
    async def parse(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """主解析方法"""
        try:
            url = raw_data.get('url', '')
            content = raw_data.get('content', '')
            
            if not content:
                logger.warning(f"空内容，跳过解析: {url}")
                return None
            
            # 根据URL或元数据确定数据类型
            source_type = self.detect_source_type(url, raw_data)
            
            # 调用对应的解析器
            parser_func = self.parsers.get(source_type, self.parse_generic)
            parsed_data = await parser_func(raw_data)
            
            if parsed_data:
                logger.info(f"解析完成: {url} - {source_type}")
            
            return parsed_data
            
        except Exception as e:
            logger.error(f"数据解析失败: {str(e)}")
            return None
    
    def detect_source_type(self, url: str, raw_data: Dict[str, Any]) -> str:
        """检测数据源类型"""
        url_patterns = {
            'government_tender': ['ccgp.gov.cn', 'ggzy.gov.cn'],
            'patent': ['patents.google.com', 'zhihuiya.com'],
            'regulation': ['miit.gov.cn', 'mee.gov.cn'],
            'market_report': ['bloomberg.com', 'ihs.com']
        }
        
        for source_type, patterns in url_patterns.items():
            if any(pattern in url for pattern in patterns):
                return source_type
        
        return 'generic'
    
    async def parse_government_tender(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """解析政府招标数据"""
        try:
            soup = BeautifulSoup(raw_data['content'], 'html.parser')
            
            # 提取标题
            title = ''
            title_selectors = ['h1', '.title', '#title', '[class*="title"]']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break
            
            # 提取正文内容
            content = ''
            content_selectors = ['.content', '#content', '.main', '[class*="content"]']
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text().strip()
                    break
            
            if not content:
                content = soup.get_text()
            
            # 提取关键信息
            metadata = self.extract_tender_metadata(content)
            
            # NLP处理
            entities = self.nlp_processor.extract_entities(content)
            relations = self.nlp_processor.extract_relations(content, entities)
            
            return ParsedData(
                source_url=raw_data['url'],
                source_type='government_tender',
                title=title,
                content=content,
                entities=entities,
                relations=relations,
                metadata=metadata,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"招标数据解析失败: {str(e)}")
            return None
    
    def extract_tender_metadata(self, content: str) -> Dict[str, Any]:
        """提取招标相关元数据"""
        metadata = {}
        
        # 提取项目规模
        scale_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:万元|万|亿元|亿)',
            r'预算.*?(\d+(?:\.\d+)?)\s*(?:万元|万|亿元|亿)',
            r'金额.*?(\d+(?:\.\d+)?)\s*(?:万元|万|亿元|亿)'
        ]
        
        for pattern in scale_patterns:
            match = re.search(pattern, content)
            if match:
                metadata['project_scale'] = match.group(1)
                break
        
        # 提取截止时间
        date_patterns = [
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4}-\d{1,2}-\d{1,2})',
            r'截止.*?(\d{4}年\d{1,2}月\d{1,2}日)',
            r'deadline.*?(\d{4}-\d{1,2}-\d{1,2})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, content)
            if match:
                metadata['deadline'] = match.group(1)
                break
        
        # 提取技术要求
        tech_keywords = ['储能', '电池', '锂离子', '钠离子', '固态', '能量密度', '循环寿命']
        tech_requirements = []
        
        for keyword in tech_keywords:
            if keyword in content:
                # 提取包含关键词的句子
                sentences = content.split('。')
                for sentence in sentences:
                    if keyword in sentence:
                        tech_requirements.append(sentence.strip())
        
        metadata['tech_requirements'] = tech_requirements
        
        return metadata
    
    async def parse_patent(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """解析专利数据"""
        try:
            # 专利数据通常是JSON格式
            if raw_data['content'].strip().startswith('{'):
                patent_data = json.loads(raw_data['content'])
            else:
                # HTML格式的专利页面
                soup = BeautifulSoup(raw_data['content'], 'html.parser')
                patent_data = self.extract_patent_from_html(soup)
            
            title = patent_data.get('title', '')
            abstract = patent_data.get('abstract', '')
            content = f"{title}\n{abstract}"
            
            # 提取专利特有的元数据
            metadata = {
                'patent_number': patent_data.get('patent_number'),
                'inventors': patent_data.get('inventors', []),
                'assignee': patent_data.get('assignee'),
                'filing_date': patent_data.get('filing_date'),
                'publication_date': patent_data.get('publication_date'),
                'ipc_classes': patent_data.get('ipc_classes', [])
            }
            
            # NLP处理
            entities = self.nlp_processor.extract_entities(content)
            relations = self.nlp_processor.extract_relations(content, entities)
            
            return ParsedData(
                source_url=raw_data['url'],
                source_type='patent',
                title=title,
                content=content,
                entities=entities,
                relations=relations,
                metadata=metadata,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"专利数据解析失败: {str(e)}")
            return None
    
    def extract_patent_from_html(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """从HTML页面提取专利信息"""
        patent_data = {}
        
        # 根据Google Patents的页面结构提取信息
        title_elem = soup.select_one('h1[data-qa="title"]')
        if title_elem:
            patent_data['title'] = title_elem.get_text().strip()
        
        abstract_elem = soup.select_one('[data-qa="abstract"]')
        if abstract_elem:
            patent_data['abstract'] = abstract_elem.get_text().strip()
        
        # 提取更多专利信息...
        
        return patent_data
    
    async def parse_regulation(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """解析法律法规数据"""
        # 实现法规解析逻辑
        pass
    
    async def parse_supplier_data(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """解析供应商数据"""
        # 实现供应商数据解析逻辑
        pass
    
    async def parse_market_report(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """解析市场报告数据"""
        # 实现市场报告解析逻辑
        pass
    
    async def parse_generic(self, raw_data: Dict[str, Any]) -> Optional[ParsedData]:
        """通用解析器"""
        try:
            soup = BeautifulSoup(raw_data['content'], 'html.parser')
            
            # 基础信息提取
            title = soup.title.get_text() if soup.title else ''
            content = soup.get_text()
            
            # NLP处理
            entities = self.nlp_processor.extract_entities(content)
            relations = self.nlp_processor.extract_relations(content, entities)
            
            return ParsedData(
                source_url=raw_data['url'],
                source_type='generic',
                title=title,
                content=content,
                entities=entities,
                relations=relations,
                metadata={},
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"通用解析失败: {str(e)}")
            return None


# 全局数据解析器实例
data_parser = DataParser()