/*
 * 投放配置的 AI 生成
 * -------------------------------------------------------------
 * 按一份投放配置(品类 / 市场 / 受众 / 目标 / 渠道 + 产品说明),
 * 让 Claude 生成:广告文案、欢迎语、兴趣词、素材方向、口播脚本。
 *
 * 口播脚本是给真人视频用的——Claude 只出脚本文字,
 * 真正把脚本渲染成视频要另外接 HeyGen 那类服务(见 README)。
 *
 * key 放 .env 里的 ANTHROPIC_API_KEY,不配就直接报错,不会瞎跑。
 */
'use strict';

const AnthropicPkg = require('@anthropic-ai/sdk');
const Anthropic = AnthropicPkg.default || AnthropicPkg;
const { z } = require('zod');
const { zodOutputFormat } = require('@anthropic-ai/sdk/helpers/zod');

const MODEL = process.env.AI_MODEL || 'claude-opus-5-5';
// 价格($/百万 token),用来估算每次花了多少钱。改模型记得一起改。
const PRICE = { in: 4.0, out: 20.0 };

/* ---------------- 输出结构 ----------------
   用结构化输出,模型必须按这个形状返回,不用自己解析文本 */
const OutputSchema = z.object({
  copy: z.array(z.object({
    hook: z.string().describe('钩子类型:价格 / 信任 / 场景 / 痛点 / 社会证明'),
    text: z.string().describe('广告正文，用投放市场的语言写'),
    note: z.string().describe('一句中文说明：这条打的是什么点'),
  })).describe('广告文案，6 条'),
  welcome: z.array(z.object({
    scene: z.string().describe('适用场景，如 CTWA 首次进线 / 落地页留资后'),
    text: z.string().describe('欢迎语正文，用投放市场的语言'),
  })).describe('欢迎语，3 条'),
  interests: z.array(z.string()).describe('广告平台的兴趣定向词，20-30 个，用平台实际使用的语言（Meta 一般是英文）'),
  creative: z.array(z.string()).describe('素材方向，中文，4-6 条，具体到拍什么、前 3 秒给什么'),
  script: z.array(z.object({
    title: z.string().describe('脚本名，中文'),
    seconds: z.number().describe('时长，秒'),
    lines: z.string().describe('口播台词，用投放市场的语言，分句换行'),
    shots: z.string().describe('镜头与画面提示，中文'),
  })).describe('真人口播脚本，2 条，一条 15 秒一条 30 秒'),
});

const SYSTEM = `你是东南亚和东非市场的广告投放操盘手，给代运营团队写投放物料。

硬性要求：
- 广告文案、欢迎语、口播台词一律用**投放市场当地人实际会用的语言**写（东非用斯瓦希里语或英语，华人市场用中文）；兴趣定向词用广告平台实际使用的语言（Meta 一般是英文）。
- 不要写成"AI 味"的模板腔。本地化的具体细节（支付方式、物流习惯、称呼、节日）比形容词重要。
- 不编造虚假承诺、假销量、假评价、假资质。需要具体数字的地方用 {数量} {城市} 这样的花括号占位，让人填。
- 合规：不写夸大疗效、保证收益、绝对化用语这类会被平台拒审的表述。
- 文案要能直接用，不要写"建议你可以..."这种说明文。`;

function buildPrompt(b) {
  const L = [];
  const add = (k, v) => { if (v && String(v).trim()) L.push(`${k}：${String(v).trim()}`); };
  add('项目/站点', b.project);
  add('品类', b.vertical);
  add('广告目标', b.objective);
  add('主渠道', b.channel);
  add('目标市场与语言', b.market);
  add('受众定向', b.audience);
  add('已有兴趣词', b.interests);
  add('投放节奏', b.pacing);
  add('产品/服务说明', b.product);
  add('补充要求', b.extra);
  return `给下面这个项目出一套投放物料。\n\n${L.join('\n')}\n\n`
    + `注意：主渠道是「${b.channel || '未填'}」，欢迎语和文案的落点要跟这个渠道对得上`
    + `（CTWA 落到 WhatsApp 对话，落地页落到表单留资）。`;
}

/* 把 zod 的字段名换成控制台里的中文字段，方便直接填表单 */
function toFields(out) {
  return {
    copy: out.copy.map((c, i) => `${i + 1}. [${c.hook}] ${c.text}\n   （${c.note}）`).join('\n\n'),
    welcome: out.welcome.map(w => `[${w.scene}]\n${w.text}`).join('\n\n'),
    interests: out.interests.join(', '),
    creative: out.creative.map((c, i) => `${i + 1}. ${c}`).join('\n'),
    script: out.script.map(s => `【${s.title}·${s.seconds}秒】\n台词：\n${s.lines}\n画面：${s.shots}`).join('\n\n'),
  };
}

/**
 * 生成物料。
 * @param {object} brief  投放配置字段 + product/extra
 * @param {object} [opts] { client } 测试时可以塞一个假的客户端进来
 */
async function generate(brief, opts = {}) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!opts.client && !apiKey) {
    const e = new Error('还没配置 Claude API key。在服务器上把 ANTHROPIC_API_KEY 写进 /opt/runadops-api/.env，然后 pm2 restart runadops-api');
    e.code = 'NO_KEY';
    throw e;
  }
  const client = opts.client || new Anthropic({ apiKey });

  const res = await client.messages.parse({
    model: MODEL,
    max_tokens: 16000,
    system: SYSTEM,
    messages: [{ role: 'user', content: buildPrompt(brief) }],
    output_config: { format: zodOutputFormat(OutputSchema) },
  });

  if (res.stop_reason === 'refusal') {
    const e = new Error('模型拒绝了这个请求' + (res.stop_details?.explanation ? '：' + res.stop_details.explanation : ''));
    e.code = 'REFUSAL';
    throw e;
  }
  if (!res.parsed_output) {
    const e = new Error('模型返回的内容解析不了,再试一次');
    e.code = 'PARSE_FAILED';
    throw e;
  }

  const u = res.usage || {};
  const cost = ((u.input_tokens || 0) / 1e6) * PRICE.in + ((u.output_tokens || 0) / 1e6) * PRICE.out;

  return {
    raw: res.parsed_output,
    fields: toFields(res.parsed_output),
    usage: {
      model: res.model || MODEL,
      input_tokens: u.input_tokens || 0,
      output_tokens: u.output_tokens || 0,
      cost_usd: Math.round(cost * 10000) / 10000,
    },
  };
}

module.exports = { generate, OutputSchema, buildPrompt, toFields, MODEL };
