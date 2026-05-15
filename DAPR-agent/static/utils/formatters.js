// 辅助函数：解码转义字符（双重解码，处理LLM返回的转义JSON）
export function decodeEscapedChars(str) {
    if (typeof str !== 'string') return str;
    
    // 处理各种转义序列
    return str
        .split('\\n').join('\n')
        .split('\\t').join('\t')
        .split('\\"').join('"')
        .split("\\'").join("'")
        .split('\\\\').join('\\');
}

// 辅助函数：格式化分析结果（适配新格式，支持Thinking和Instruct模型，兼容中英文字段）
export function formatAnalysisResult(data) {
    let html = '';
    
    // 调试信息
    console.log('[formatAnalysisResult] input data:', data);
    
    // 检查数据有效性
    if (!data || typeof data !== 'object') {
        console.error('[formatAnalysisResult] Invalid data:', data);
        return '<p style="color:#ff6b6b;">⚠️ 数据格式错误：' + JSON.stringify(data).slice(0, 200) + '</p>';
    }
    
    // 检查是否为Thinking模型（有think字段）
    const isThinkingModel = data.think && typeof data.think === 'string';
    
    // Thinking模型：显示思考过程（可折叠）
    if (isThinkingModel) {
        html += `
            <div style="margin-bottom:15px;">
                <details style="background:#1a1a2e;border:1px solid #0f3460;border-radius:6px;overflow:hidden;">
                    <summary style="padding:12px 15px;cursor:pointer;background:#16213e;color:#ffc107;font-size:0.95rem;display:flex;align-items:center;gap:8px;">
                        <span>💭</span>
                        <span><strong>查看模型思考过程</strong></span>
                        <span style="margin-left:auto;font-size:0.8rem;color:#888;">点击展开 ▼</span>
                    </summary>
                    <div style="padding:15px;border-top:1px solid #0f3460;">
                        <pre style="margin:0;color:#aaa;font-size:0.85rem;line-height:1.6;white-space:pre-wrap;max-height:400px;overflow-y:auto;">${decodeEscapedChars(data.think)}</pre>
                    </div>
                </details>
            </div>
        `;
    }
    
    // 适配新的 analysis 结构（支持中英文键名）
    const analysis = data.analysis || data;
    
    // 获取字段值的辅助函数（支持中英文键名）
    function getField(obj, enKey, cnKey) {
        return obj[enKey] || obj[cnKey] || null;
    }
    
    // 绘画特征分析（支持中英文键名）
    const drawingFeatures = getField(analysis, 'drawing_features', '绘画特征分析') || 
                           getField(analysis, 'drawingFeatures', '绘画特征');
    if (drawingFeatures) {
        const df = drawingFeatures;
        html += `
            <div style="background:#16213e;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 10px 0;color:#e94560;font-size:1rem;"><strong>🎨 绘画特征分析</strong></p>
                ${(getField(df, 'person_size_and_position', '人物大小与位置')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">人物大小与位置</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(df, 'person_size_and_position', '人物大小与位置'))}</p></div>` : ''}
                ${(getField(df, 'line_quality', '线条特征')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">线条特征</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(df, 'line_quality', '线条特征'))}</p></div>` : ''}
                ${(getField(df, 'rain_representation', '雨的描绘')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">雨的描绘</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(df, 'rain_representation', '雨的描绘'))}</p></div>` : ''}
                ${(getField(df, 'defensive_objects', '防御/遮蔽物')) ? `<div><span style="color:#888;font-size:0.85rem;">防御/遮蔽物</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(df, 'defensive_objects', '防御/遮蔽物'))}</p></div>` : ''}
            </div>
        `;
    }
    
    // 过程分析（支持中英文键名）
    const processAnalysis = getField(analysis, 'process_analysis', '过程分析') ||
                           getField(analysis, 'processAnalysis', '绘画过程分析');
    if (processAnalysis) {
        const pa = processAnalysis;
        html += `
            <div style="background:#16213e;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 10px 0;color:#17a2b8;font-size:1rem;"><strong>🔄 绘画过程分析</strong></p>
                ${(getField(pa, 'drawing_sequence', '绘画顺序')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">绘画顺序</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(pa, 'drawing_sequence', '绘画顺序'))}</p></div>` : ''}
                ${(getField(pa, 'erasures_and_modifications', '涂改情况')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">涂改情况</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(pa, 'erasures_and_modifications', '涂改情况'))}</p></div>` : ''}
                ${(getField(pa, 'time_distribution', '耗时分布')) ? `<div><span style="color:#888;font-size:0.85rem;">耗时分布</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(pa, 'time_distribution', '耗时分布'))}</p></div>` : ''}
            </div>
        `;
    }
    
    // 表情分析（支持中英文键名）
    const expressionAnalysis = getField(analysis, 'expression_analysis', '表情分析') ||
                              getField(analysis, 'expressionAnalysis', '绘画表情分析');
    if (expressionAnalysis) {
        const ea = expressionAnalysis;
        html += `
            <div style="background:#16213e;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 10px 0;color:#ffc107;font-size:1rem;"><strong>😊 表情分析</strong></p>
                ${(getField(ea, 'emotional_state_during_drawing', '绘画时情绪状态')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">绘画时情绪状态</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(ea, 'emotional_state_during_drawing', '绘画时情绪状态'))}</p></div>` : ''}
                ${(getField(ea, 'focus_changes', '专注度变化')) ? `<div style="margin-bottom:8px;"><span style="color:#888;font-size:0.85rem;">专注度变化</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(ea, 'focus_changes', '专注度变化'))}</p></div>` : ''}
                ${(getField(ea, 'stress_indicators', '压力指标')) ? `<div><span style="color:#888;font-size:0.85rem;">压力指标</span><p style="margin:3px 0 0 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(getField(ea, 'stress_indicators', '压力指标'))}</p></div>` : ''}
            </div>
        `;
    }
    
    // 时序关联
    const temporalCorr = getField(analysis, 'temporal_correlation', '时序关联');
    if (temporalCorr) {
        html += `
            <div style="background:#0f3460;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 8px 0;color:#9c27b0;font-size:1rem;"><strong>⏱️ 时序关联分析</strong></p>
                <p style="margin:0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">${decodeEscapedChars(temporalCorr)}</p>
            </div>
        `;
    }
    
    // 心理猜想（支持多种可能的键名）
    const psychologicalGuesstimates = getField(data, 'psychological_guesstimates', '心理状态猜想') ||
                                     getField(data, 'psychological_guesses', '心理猜想') ||
                                     getField(data, 'hypotheses', '猜想');
    if (psychologicalGuesstimates && Array.isArray(psychologicalGuesstimates)) {
        html += `
            <div style="background:#0f3460;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 10px 0;color:#e94560;font-size:1rem;"><strong>💡 心理状态猜想</strong></p>
                <ol style="margin:0;padding-left:20px;">
                    ${psychologicalGuesstimates.map((h, i) => `
                        <li style="margin:8px 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">
                            <span style="display:inline-block;background:#e94560;color:white;padding:2px 8px;border-radius:4px;font-size:0.75rem;margin-right:8px;">${i+1}</span>
                            ${decodeEscapedChars(h)}
                        </li>
                    `).join('')}
                </ol>
            </div>
        `;
    }
    
    // 询问问题（支持多种可能的键名）
    const questionsForUser = getField(data, 'questions_for_user', '询问用户的问题') ||
                            getField(data, 'questions', '问题') ||
                            getField(data, 'questionsToAsk', '提问');
    if (questionsForUser && Array.isArray(questionsForUser)) {
        html += `
            <div style="background:#16213e;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 10px 0;color:#17a2b8;font-size:1rem;"><strong>❓ 建议询问的问题</strong></p>
                <ol style="margin:0;padding-left:20px;">
                    ${questionsForUser.map((q, i) => `
                        <li style="margin:8px 0;color:#ddd;font-size:0.9rem;line-height:1.5;white-space:pre-wrap;">
                            ${decodeEscapedChars(q)}
                        </li>
                    `).join('')}
                </ol>
            </div>
        `;
    }
    
    // 用户信息请求
    const userInfoRequest = getField(data, 'user_information_request', '用户信息请求') ||
                           getField(data, 'userInfoRequest', '基本信息');
    if (userInfoRequest) {
        const uir = userInfoRequest;
        html += `
            <div style="background:#16213e;padding:12px;border-radius:6px;margin-bottom:10px;">
                <p style="margin:0 0 8px 0;color:#28a745;font-size:1rem;"><strong>👤 建议收集的基本信息</strong></p>
                <div style="display:flex;gap:15px;">
                    ${(getField(uir, 'age_range', '年龄段')) ? `<div><span style="color:#888;font-size:0.85rem;">年龄段</span><p style="margin:3px 0 0 0;color:#ddd;">${decodeEscapedChars(getField(uir, 'age_range', '年龄段'))}</p></div>` : ''}
                    ${(getField(uir, 'gender', '性别')) ? `<div><span style="color:#888;font-size:0.85rem;">性别</span><p style="margin:3px 0 0 0;color:#ddd;">${decodeEscapedChars(getField(uir, 'gender', '性别'))}</p></div>` : ''}
                </div>
            </div>
        `;
    }
    
    // 如果没有生成任何内容，显示调试信息
    if (!html) {
        console.error('[formatAnalysisResult] No content generated for data:', data);
        return `
            <p style="color:#ff6b6b;">⚠️ 无法解析分析内容</p>
            <details style="margin-top:10px;">
                <summary style="color:#888;cursor:pointer;">查看原始数据</summary>
                <pre style="background:#1a1a2e;padding:10px;border-radius:4px;color:#aaa;font-size:0.8rem;overflow-x:auto;">${JSON.stringify(data, null, 2).slice(0, 2000)}</pre>
            </details>
        `;
    }
    
    return html;
}

// 格式化日志内容
export function formatLogContent(log) {
    const sections = [];
    
    // 根据阶段格式化输出
    switch (log.stage) {
        case 'initial_analysis':
            if (log.llm_output) {
                const output = log.llm_output;
                // 检查是否有 raw_response（LLM返回的非结构化文本）
                if (output.raw_response) {
                    // 先解码 raw_response 本身
                    const decodedRaw = decodeEscapedChars(output.raw_response);
                    
                    // 尝试从 decodedRaw 提取 JSON
                    try {
                        const jsonMatch = decodedRaw.match(/\{[\s\S]*\}/);
                        if (jsonMatch) {
                            const parsed = JSON.parse(jsonMatch[0]);
                            
                            // 递归解码 parsed 对象中的所有字符串值
                            function deepDecode(obj) {
                                if (typeof obj === 'string') {
                                    return decodeEscapedChars(obj);
                                } else if (Array.isArray(obj)) {
                                    return obj.map(deepDecode);
                                } else if (typeof obj === 'object' && obj !== null) {
                                    const result = {};
                                    for (const [key, value] of Object.entries(obj)) {
                                        result[key] = deepDecode(value);
                                    }
                                    return result;
                                }
                                return obj;
                            }
                            
                            const fullyDecoded = deepDecode(parsed);
                            
                            // Thinking模型格式：{think, analysis}；Instruct模型格式：{analysis} 或扁平结构
                            const resultData = fullyDecoded.analysis ? fullyDecoded : { analysis: fullyDecoded };
                            
                            sections.push(`
                                <div class="log-section">
                                    <div class="log-section-title">🧠 DAPR分析结论</div>
                                    <div class="log-content readable">
                                        ${formatAnalysisResult(resultData)}
                                    </div>
                                </div>
                            `);
                        } else {
                            // 显示文本摘要
                            const summary = decodedRaw.slice(0, 800);
                            sections.push(`
                                <div class="log-section">
                                    <div class="log-section-title">🧠 DAPR分析结论</div>
                                    <div class="log-content readable" style="white-space:pre-wrap;line-height:1.6;">
                                        ${summary}${decodedRaw.length > 800 ? '...' : ''}
                                    </div>
                                </div>
                            `);
                        }
                    } catch (e) {
                        // 显示原始文本
                        const summary = decodedRaw.slice(0, 800);
                        sections.push(`
                            <div class="log-section">
                                <div class="log-section-title">🧠 DAPR分析结论</div>
                                <div class="log-content readable" style="white-space:pre-wrap;line-height:1.6;">
                                    ${summary}${decodedRaw.length > 800 ? '...' : ''}
                                </div>
                            </div>
                        `);
                    }
                } else {
                    // 使用结构化数据 - 使用 formatAnalysisResult 统一处理
                    const formattedResult = formatAnalysisResult(output);
                    
                    sections.push(`
                        <div class="log-section">
                            <div class="log-section-title">🧠 DAPR分析结论</div>
                            <div class="log-content readable">
                                ${formattedResult}
                            </div>
                        </div>
                    `);
                }
            }
            break;
            
        case 'analysis_stream_complete':
            // 流式分析完成，显示最终结果（支持Thinking模型）
            if (log.llm_output && log.llm_output.result) {
                const result = log.llm_output.result;
                
                // 准备显示的数据 - 对于Thinking模型，传递整个result（包含think字段）；否则传递analysis或result
                // formatAnalysisResult 函数内部会处理 think 字段的显示，不需要在这里重复处理
                const displayData = result.think ? result : (result.analysis || result);
                
                console.log('[Debug] analysis_stream_complete result:', result);
                console.log('[Debug] displayData:', displayData);
                
                // formatAnalysisResult 已经包含了思考过程的显示，直接调用即可
                const formattedResult = formatAnalysisResult(displayData);
                
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🧠 DAPR分析结论（流式）</div>
                        <div class="log-content readable">
                            ${formattedResult}
                        </div>
                    </div>
                `);
            } else {
                console.log('[Debug] analysis_stream_complete - no result:', log);
            }
            break;
            
        case 'user_answers':
            if (log.data && log.data.answers) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">💬 受试者回答</div>
                        <div class="log-content readable">
                            ${log.data.questions ? `
                                ${log.data.questions.map((q, i) => `
                                    <div style="margin:10px 0;padding:10px;background:#0f3460;border-radius:4px;">
                                        <p style="white-space:pre-wrap;line-height:1.4;"><strong>Q${i+1}: ${decodeEscapedChars(q)}</strong></p>
                                        <p style="color:#e94560;margin-top:5px;white-space:pre-wrap;line-height:1.4;">A: ${decodeEscapedChars(log.data.answers[i]) || '(未回答)'}</p>
                                    </div>
                                `).join('')}
                            ` : `
                                <ol>
                                    ${log.data.answers.map((a, i) => `<li style="margin:8px 0;white-space:pre-wrap;line-height:1.4;"><strong>回答:</strong> ${decodeEscapedChars(a)}</li>`).join('')}
                                </ol>
                            `}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'generate_instructions':
            if (log.llm_output && log.llm_output.variations) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🎨 编辑指令生成</div>
                        <div class="log-content readable">
                            <p><strong>生成了 ${log.llm_output.variations.length} 个图像变体：</strong></p>
                            ${log.llm_output.variations.map((v, i) => `
                                <div style="margin: 10px 0; padding: 10px; background: #0f3460; border-radius: 4px;">
                                    <p><strong>变体 ${i+1}: ${v.name}</strong></p>
                                    <p>描述：${v.description}</p>
                                    <p style="color: #aaa; font-size: 0.85rem; margin-top: 5px;">
                                        <strong>Flux2编辑提示词：</strong>${v.edit_prompt || v.prompt || '无'}
                                    </p>
                                    <p style="color: #aaa; font-size: 0.85rem;">
                                        <strong>上色提示词：</strong>${v.color_prompt || '无'}
                                    </p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'image_generation':
            if (log.flux2_output && log.flux2_output.generated_images) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🖼️ 图像生成结果</div>
                        <div class="log-content readable">
                            <p>成功生成 ${log.flux2_output.generated_images.length} 张图像</p>
                            ${log.flux2_output.generated_images.map(img => `
                                <div style="margin: 10px 0;">
                                    <p><strong>${img.name}</strong></p>
                                    <p style="color: #888; font-size: 0.85rem;">${img.description}</p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'final_questions_generated':
            if (log.llm_output && log.llm_output.questions) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">❓ 最终深入问题</div>
                        <div class="log-content readable">
                            <p><strong>基于用户选择生成的问题：</strong></p>
                            <ol>
                                ${log.llm_output.questions.map(q => `<li style="white-space:pre-wrap;line-height:1.4;">${decodeEscapedChars(q)}</li>`).join('')}
                            </ol>
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'final_report':
            if (log.llm_output) {
                const r = log.llm_output;
                const insights = r.creative_insights || r.key_insights || [];
                const explorations = r.suggested_explorations || r.recommendations || [];
                
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🎨 创作回顾</div>
                        <div class="log-content readable">
                            ${r.summary ? `
                                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                                    <p style="margin:0;color:white;font-size:1.05rem;"><strong>💬 整体感受</strong></p>
                                    <p style="margin:10px 0 0 0;color:white;line-height:1.6;white-space:pre-wrap;">${decodeEscapedChars(r.summary)}</p>
                                </div>
                            ` : ''}
                            
                            ${insights.length ? `
                                <div style="margin-bottom: 15px;">
                                    <p style="color: #aaa; font-size: 0.9rem; margin-bottom: 8px;"><strong>💡 创作洞察</strong></p>
                                    <ul style="margin: 0; padding-left: 20px;">
                                        ${insights.map(i => `<li style="margin: 6px 0; color: #ddd; line-height: 1.5; white-space: pre-wrap;">${decodeEscapedChars(i)}</li>`).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                            
                            ${explorations.length ? `
                                <div>
                                    <p style="color: #aaa; font-size: 0.9rem; margin-bottom: 8px;"><strong>🌱 探索建议</strong></p>
                                    <div style="display: flex; flex-direction: column; gap: 8px;">
                                        ${explorations.map((rec, i) => `
                                            <div style="background: #e8f5e9; padding: 10px 12px; border-radius: 6px; border-left: 4px solid #4caf50;">
                                                <span style="background: #4caf50; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 8px;">${i+1}</span>
                                                <span style="color: #2e7d32; white-space: pre-wrap; line-height: 1.4;">${decodeEscapedChars(rec)}</span>
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'image_selection':
            if (log.data && log.data.selection_behavior) {
                const sb = log.data.selection_behavior;
                const finalSel = sb.finalSelection || {};
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🎯 图像选择行为</div>
                        <div class="log-content readable">
                            <p><strong>最终选择：</strong>${finalSel.imageName || 'N/A'} (第${finalSel.viewOrder || '?'}个查看)</p>
                            <p><strong>查看顺序：</strong>${(sb.viewOrder || []).join(' → ')}</p>
                            <p><strong>总查看数：</strong>${finalSel.totalViews || sb.viewOrder?.length || 0}</p>
                            ${sb.hesitationIndicators?.length > 0 ? `
                                <p><strong>⚠️ 犹豫行为：</strong></p>
                                <ul>
                                    ${sb.hesitationIndicators.map(h => `<li>${h.description || h.type}</li>`).join('')}
                                </ul>
                            ` : '<p><strong>犹豫行为：</strong>未发现明显犹豫</p>'}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'generate_instructions':
            if (log.llm_output && log.llm_output.variations) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">🎨 图像变体生成</div>
                        <div class="log-content readable">
                            <p>生成了 ${log.llm_output.variations.length} 个变体：</p>
                            ${log.llm_output.variations.map((v, i) => `
                                <div style="margin: 10px 0; padding: 10px; background: #0f3460; border-radius: 4px;">
                                    <p><strong>变体 ${i+1}: ${v.name}</strong></p>
                                    <p style="color: #aaa;">${v.description}</p>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `);
            }
            break;
            
        case 'final_questions_generated':
            if (log.llm_output && log.llm_output.questions) {
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">❓ 深入问题</div>
                        <div class="log-content readable">
                            <ol>
                                ${log.llm_output.questions.map(q => `<li>${q}</li>`).join('')}
                            </ol>
                        </div>
                    </div>
                `);
            }
            break;
            
        default:
            // 默认情况：智能格式化显示
            if (log.llm_output && Object.keys(log.llm_output).length > 0) {
                const output = log.llm_output;
                let content = '';
                let parsedFromRaw = null;
                
                // 检查是否有 raw_response 字段（LLM返回的原始文本）
                if (output.raw_response && typeof output.raw_response === 'string') {
                    // 尝试从 raw_response 中提取 JSON
                    try {
                        const jsonMatch = output.raw_response.match(/\{[\s\S]*\}/);
                        if (jsonMatch) {
                            parsedFromRaw = JSON.parse(jsonMatch[0]);
                        }
                    } catch (e) {
                        // 解析失败，使用原始文本
                        parsedFromRaw = null;
                    }
                    
                    // 如果解析成功，使用解析后的数据
                    if (parsedFromRaw) {
                        content = formatAnalysisResult(parsedFromRaw);
                    } else {
                        // 显示原始文本的摘要（前500字符）
                        const summary = output.raw_response.slice(0, 500);
                        content = `
                            <div style="background:#1a1a2e;padding:12px;border-radius:6px;margin-bottom:10px;">
                                <p style="margin:0;color:#ddd;line-height:1.6;white-space:pre-wrap;">${summary}${output.raw_response.length > 500 ? '...' : ''}</p>
                            </div>
                        `;
                    }
                }
                
                // 如果没有从 raw_response 获取到内容，尝试其他字段
                if (!content) {
                    if (output.summary || output.analysis_summary) {
                        content += `<p><strong>摘要：</strong>${output.summary || output.analysis_summary}</p>`;
                    }
                    if (output.questions && Array.isArray(output.questions)) {
                        content += `<p><strong>问题：</strong></p><ol>${output.questions.map(q => `<li>${q}</li>`).join('')}</ol>`;
                    }
                    if (output.hypotheses && Array.isArray(output.hypotheses)) {
                        content += `<p><strong>猜想：</strong></p><ul>${output.hypotheses.map(h => `<li>${h.description || h} (${h.confidence || '未知'})</li>`).join('')}</ul>`;
                    }
                    if (output.variations && Array.isArray(output.variations)) {
                        content += `<p><strong>变体：</strong>${output.variations.map(v => v.name).join('、')}</p>`;
                    }
                }
                
                // 如果还是没内容，显示折叠的原始数据
                if (!content) {
                    content = `
                        <p style="color:#888;font-size:0.85rem;">暂无可预览内容</p>
                        <details style="margin-top:10px;">
                            <summary style="cursor:pointer;color:#e94560;font-size:0.85rem;">查看原始数据</summary>
                            <pre style="margin-top:10px;font-size:0.75rem;opacity:0.7;max-height:300px;overflow:auto;">${JSON.stringify(output, null, 2)}</pre>
                        </details>
                    `;
                }
                
                sections.push(`
                    <div class="log-section">
                        <div class="log-section-title">📄 ${log.stage || '分析结果'}</div>
                        <div class="log-content readable">
                            ${content}
                        </div>
                    </div>
                `);
            } else if (log.data) {
                // 显示 data 字段的内容
                let dataContent = '';
                for (const [key, value] of Object.entries(log.data)) {
                    if (typeof value === 'string') {
                        dataContent += `<p><strong>${key}:</strong> ${value}</p>`;
                    } else if (Array.isArray(value)) {
                        dataContent += `<p><strong>${key}:</strong> ${value.join('、')}</p>`;
                    } else if (typeof value === 'object' && value !== null) {
                        // 对象类型折叠显示
                        dataContent += `
                            <details style="margin:5px 0;">
                                <summary style="cursor:pointer;color:#aaa;">${key}</summary>
                                <pre style="font-size:0.8rem;margin:5px 0;padding:5px;background:#0f3460;border-radius:4px;">${JSON.stringify(value, null, 2)}</pre>
                            </details>
                        `;
                    }
                }
                if (dataContent) {
                    sections.push(`
                        <div class="log-section">
                            <div class="log-section-title">📊 ${log.stage || '数据'}</div>
                            <div class="log-content readable">${dataContent}</div>
                        </div>
                    `);
                }
            }
    }
    
    return sections.join('');
}
