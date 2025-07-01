"""
智能问答API路由
提供基于RAG的智能问答服务
"""

from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...ai_models.qa_system import qa_system
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class QuestionRequest(BaseModel):
    """问题请求模型"""
    question: str = Field(..., description="用户问题", example="欧盟2025年电池碳足迹门槛是什么？")
    confidence_threshold: float = Field(default=0.9, description="置信度阈值", ge=0.0, le=1.0)
    include_sources: bool = Field(default=True, description="是否包含信息来源")
    include_entities: bool = Field(default=True, description="是否包含相关实体")


class QuestionResponse(BaseModel):
    """问题回答模型"""
    question: str = Field(..., description="原始问题")
    answer: str = Field(..., description="答案内容")
    confidence: float = Field(..., description="置信度")
    meets_threshold: bool = Field(..., description="是否达到置信度阈值")
    sources: List[Dict[str, Any]] = Field(default=[], description="信息来源")
    entities: List[Dict[str, Any]] = Field(default=[], description="相关实体")
    processing_time: float = Field(..., description="处理时间（秒）")
    timestamp: str = Field(..., description="处理时间戳")
    improvement_suggestions: Optional[List[str]] = Field(default=None, description="改进建议")


class BatchQuestionRequest(BaseModel):
    """批量问题请求模型"""
    questions: List[str] = Field(..., description="问题列表")
    confidence_threshold: float = Field(default=0.9, description="置信度阈值")


@router.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """
    智能问答接口
    
    基于RAG架构，结合知识图谱生成解释性答案
    """
    try:
        logger.info(f"收到问题: {request.question}")
        
        result = await qa_system.answer_question(
            query=request.question,
            confidence_threshold=request.confidence_threshold
        )
        
        # 根据请求选项过滤结果
        if not request.include_sources:
            result["sources"] = []
        
        if not request.include_entities:
            result["entities"] = []
        
        response = QuestionResponse(
            question=request.question,
            answer=result["answer"],
            confidence=result["confidence"],
            meets_threshold=result["meets_threshold"],
            sources=result["sources"],
            entities=result["entities"],
            processing_time=0.0,  # TODO: 从result中获取
            timestamp=result["timestamp"],
            improvement_suggestions=result.get("improvement_suggestions")
        )
        
        logger.info(f"问题处理完成，置信度: {result['confidence']:.2f}")
        
        return response
        
    except Exception as e:
        logger.error(f"问题处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"问题处理失败: {str(e)}")


@router.post("/batch", response_model=List[QuestionResponse])
async def batch_questions(request: BatchQuestionRequest):
    """
    批量问答接口
    
    并发处理多个问题
    """
    try:
        logger.info(f"收到批量问题: {len(request.questions)} 个")
        
        results = await qa_system.batch_process_questions(request.questions)
        
        responses = []
        for i, result in enumerate(results):
            if result.get("error"):
                response = QuestionResponse(
                    question=request.questions[i],
                    answer=result["answer"],
                    confidence=0.0,
                    meets_threshold=False,
                    sources=[],
                    entities=[],
                    processing_time=0.0,
                    timestamp=result.get("timestamp", ""),
                    improvement_suggestions=["请检查问题格式并重试"]
                )
            else:
                response = QuestionResponse(
                    question=request.questions[i],
                    answer=result["answer"],
                    confidence=result["confidence"],
                    meets_threshold=result["meets_threshold"],
                    sources=result["sources"],
                    entities=result["entities"],
                    processing_time=0.0,
                    timestamp=result["timestamp"],
                    improvement_suggestions=result.get("improvement_suggestions")
                )
            responses.append(response)
        
        logger.info(f"批量问题处理完成: {len(responses)} 个")
        
        return responses
        
    except Exception as e:
        logger.error(f"批量问题处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"批量问题处理失败: {str(e)}")


@router.get("/examples")
async def get_examples():
    """
    获取预定义问题示例
    """
    try:
        examples = await qa_system.get_predefined_answers()
        return examples
        
    except Exception as e:
        logger.error(f"获取示例失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取示例失败: {str(e)}")


@router.get("/statistics")
async def get_statistics():
    """
    获取问答系统统计信息
    """
    try:
        stats = qa_system.get_query_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/test", response_class=HTMLResponse)
async def test_interface():
    """
    智能问答测试界面
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>智能问答测试</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
            }
            .header h1 {
                margin: 0;
                font-size: 2.5em;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .chat-container {
                background: rgba(255,255,255,0.1);
                border-radius: 15px;
                padding: 20px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255,255,255,0.2);
                margin-bottom: 20px;
            }
            .messages {
                height: 400px;
                overflow-y: auto;
                padding: 10px;
                background: rgba(0,0,0,0.2);
                border-radius: 10px;
                margin-bottom: 20px;
            }
            .message {
                margin-bottom: 15px;
                padding: 12px;
                border-radius: 10px;
                animation: fadeIn 0.3s ease-in;
            }
            .user-message {
                background: rgba(70, 130, 230, 0.8);
                margin-left: 20%;
                text-align: right;
            }
            .bot-message {
                background: rgba(50, 50, 50, 0.8);
                margin-right: 20%;
            }
            .input-area {
                display: flex;
                gap: 10px;
            }
            .question-input {
                flex: 1;
                padding: 12px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                background: rgba(255,255,255,0.9);
                color: #333;
            }
            .send-button {
                padding: 12px 24px;
                background: #FFD700;
                color: #333;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                cursor: pointer;
                transition: background 0.3s ease;
            }
            .send-button:hover {
                background: #FFC700;
            }
            .send-button:disabled {
                background: #999;
                cursor: not-allowed;
            }
            .examples {
                margin-top: 20px;
            }
            .example-button {
                display: inline-block;
                margin: 5px;
                padding: 8px 16px;
                background: rgba(255,255,255,0.2);
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                transition: background 0.3s ease;
            }
            .example-button:hover {
                background: rgba(255,255,255,0.3);
            }
            .confidence-info {
                font-size: 12px;
                color: #FFD700;
                margin-top: 5px;
            }
            .loading {
                display: none;
                text-align: center;
                padding: 10px;
                color: #FFD700;
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .spinner {
                border: 2px solid rgba(255,255,255,0.3);
                border-radius: 50%;
                border-top: 2px solid #FFD700;
                width: 20px;
                height: 20px;
                animation: spin 1s linear infinite;
                display: inline-block;
                margin-right: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 AI智能问答</h1>
                <p>基于RAG架构的电池行业智能问答系统</p>
            </div>
            
            <div class="chat-container">
                <div class="messages" id="messages">
                    <div class="message bot-message">
                        <div>您好！我是AI智能情报分析助手，专门分析电池和储能行业的商业情报。</div>
                        <div>您可以询问关于欧盟法规、供应链风险、技术趋势等问题。</div>
                        <div class="confidence-info">💡 系统置信度目标: ≥90%</div>
                    </div>
                </div>
                
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    正在分析您的问题...
                </div>
                
                <div class="input-area">
                    <input type="text" id="questionInput" class="question-input" 
                           placeholder="请输入您的问题..." maxlength="500">
                    <button id="sendButton" class="send-button">发送</button>
                </div>
                
                <div class="examples">
                    <strong>💡 示例问题:</strong><br>
                    <button class="example-button" onclick="askExample('欧盟2025年电池碳足迹门槛是什么？')">
                        欧盟电池碳足迹门槛
                    </button>
                    <button class="example-button" onclick="askExample('印尼镍矿出口限制对高镍三元电池产能有什么影响？')">
                        印尼镍矿影响分析
                    </button>
                    <button class="example-button" onclick="askExample('当前固态电池技术的主要技术路线有哪些？')">
                        固态电池技术路线
                    </button>
                    <button class="example-button" onclick="askExample('宁德时代的主要供应商风险点在哪里？')">
                        供应商风险分析
                    </button>
                </div>
            </div>
        </div>
        
        <script>
            const messagesDiv = document.getElementById('messages');
            const questionInput = document.getElementById('questionInput');
            const sendButton = document.getElementById('sendButton');
            const loadingDiv = document.getElementById('loading');
            
            function addMessage(content, isUser = false, confidence = null) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
                
                let html = `<div>${content}</div>`;
                if (confidence !== null) {
                    const confidenceColor = confidence >= 0.9 ? '#90EE90' : confidence >= 0.7 ? '#FFD700' : '#FF6B6B';
                    html += `<div class="confidence-info" style="color: ${confidenceColor}">
                        📊 置信度: ${(confidence * 100).toFixed(1)}%
                        ${confidence >= 0.9 ? '✅ 高可信' : confidence >= 0.7 ? '⚠️ 中等可信' : '❌ 低可信'}
                    </div>`;
                }
                
                messageDiv.innerHTML = html;
                messagesDiv.appendChild(messageDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
            
            async function askQuestion(question) {
                if (!question.trim()) return;
                
                // 显示用户消息
                addMessage(question, true);
                
                // 显示加载状态
                loadingDiv.style.display = 'block';
                sendButton.disabled = true;
                questionInput.disabled = true;
                
                try {
                    const response = await fetch('/qa/ask', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            question: question,
                            confidence_threshold: 0.9,
                            include_sources: true,
                            include_entities: true
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        let answer = data.answer;
                        
                        // 添加来源信息
                        if (data.sources && data.sources.length > 0) {
                            answer += '\\n\\n📎 主要来源:\\n';
                            data.sources.slice(0, 3).forEach((source, i) => {
                                answer += `${i + 1}. ${source.title || source.entity_name || '相关文档'}\\n`;
                            });
                        }
                        
                        // 添加改进建议
                        if (data.improvement_suggestions && data.improvement_suggestions.length > 0) {
                            answer += '\\n\\n💡 建议:\\n';
                            data.improvement_suggestions.forEach(suggestion => {
                                answer += `• ${suggestion}\\n`;
                            });
                        }
                        
                        addMessage(answer, false, data.confidence);
                    } else {
                        addMessage(`❌ 错误: ${data.detail || '处理失败'}`, false);
                    }
                } catch (error) {
                    addMessage(`❌ 网络错误: ${error.message}`, false);
                } finally {
                    loadingDiv.style.display = 'none';
                    sendButton.disabled = false;
                    questionInput.disabled = false;
                    questionInput.focus();
                }
            }
            
            function askExample(question) {
                questionInput.value = question;
                askQuestion(question);
            }
            
            // 事件监听器
            sendButton.addEventListener('click', () => {
                askQuestion(questionInput.value);
                questionInput.value = '';
            });
            
            questionInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    askQuestion(questionInput.value);
                    questionInput.value = '';
                }
            });
            
            // 自动聚焦
            questionInput.focus();
        </script>
    </body>
    </html>
    """
    return html_content