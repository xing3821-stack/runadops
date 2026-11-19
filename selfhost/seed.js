#!/usr/bin/env node
/*
 * 给控制台铺底:套餐报价 + 投放配置模板
 *
 *   cd /opt/runadops-api && node seed.js
 *
 * 只新增,不覆盖:同名的套餐 / 同名的投放配置已经存在就跳过。
 * 重复执行安全。塞进去之后在控制台里直接改就行。
 */
'use strict';

const path = require('node:path');
const fs = require('node:fs');
const crypto = require('node:crypto');
const mysql = require('mysql2/promise');

const ENV_FILE = path.join(__dirname, '.env');
if (fs.existsSync(ENV_FILE)) {
  for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) process.env[m[1]] = m[2];
  }
}

/* ---------------- 套餐报价 ----------------
   口径:广告一律走客户自己的广告户,我们只收服务费 / 管理费。
   计费方式只能是「月费 / 一次性 / 按广告花费%」这三种(控制台的下拉就这三个)。 */
const PACKAGES = [
  {
    name: '账户搭建 · 一次性',
    billing: '一次性',
    price: 600,
    desc: '客户自有主体开户陪跑:BM 建号与授权、Pixel/转化 API 接入、'
        + '支付卡绑定、落地页合规件(隐私政策 / 服务条款)、'
        + '域名与中间页搭建。交付后账户归客户自己所有。',
  },
  {
    name: '基础代运营 · 月费',
    billing: '月费',
    price: 800,
    desc: '单平台 1–2 条在投:受众与兴趣词配置、素材排期(AI 口播 + 实拍各若干)、'
        + '日常优化与预算调配、每周一次数据简报。不含素材拍摄与广告消耗。',
  },
  {
    name: '标准代运营 · 月费',
    billing: '月费',
    price: 1500,
    desc: '多平台(Meta + TikTok / Google)同时在投:完整投放方案、A/B 测试排期、'
        + 'WhatsApp 话术与欢迎语设计、每周数据复盘 + 月度报告、CPA/ROAS 跟踪。',
  },
  {
    name: '按广告花费抽成',
    billing: '按广告花费%',
    price: 12,
    desc: '适合月消耗较大的客户:按客户账户实际消耗的百分比收管理费,'
        + '消耗越大单位成本越低。通常设月度保底,与基础月费二选一。',
  },
];

/* ---------------- 投放配置模板 ----------------
   字段取值必须用控制台下拉里的原词,不然界面显示不出来:
     vertical  : SEO / 独立站·网购 / 盲盒 / 其他
     objective : 线索 Leads / 转化 Conversions / 消息 Messages / 流量 Traffic / App 安装 / 涨粉 Engagement
     channel   : CTWA (WhatsApp) / 落地页 Landing / IG + ManyChat / Google 搜索 / 多渠道
     status    : 草稿 / 在投 / 暂停                                               */
const BRIEFS = [
  {
    project: '【模板】东非电商 · WhatsApp 获客',
    vertical: '独立站/网购',
    objective: '消息 Messages',
    channel: 'CTWA (WhatsApp)',
    market: '坦桑尼亚 / 肯尼亚 · 斯瓦希里语为主,英语为辅',
    audience: '18–45 岁、手机为主要上网设备、习惯用 WhatsApp 谈生意和购物的本地用户。'
            + '先跑宽泛受众(Shopping / Entertainment / Sports),让算法自己找人,'
            + '出量之后再按最好的那组细分。东非精准定向标签少,窄受众反而跑不动。',
    interests: 'Online Shopping, WhatsApp, Mobile Payments, M-Pesa, Fashion, Electronics, '
             + 'Home Appliances, Deals and Discounts, Entrepreneurship',
    pacing: '目标选「消息」,优化事件选「发起对话」。开三组「受众 × 素材」各跑 5–7 天,'
          + '单组日预算 10–20 U,别急着改——学习期内频繁调预算会让投放重新学习。'
          + '挑单次对话成本最低的 1–2 组,每次加预算不超过 20%。'
          + '看「对话 → 成交」的转化率,只看对话量会被无效咨询骗。',
    welcome: 'Karibu! 👋 感谢咨询。请告诉我你想要哪一款、送到哪个城市,'
           + '我这边报价给你(含运费)。支持 M-Pesa / 货到付款。',
    copy: '① 价格钩子:本地现货,今天下单明天送到 {城市}。M-Pesa 付款或货到付款,不满意可退。\n'
        + '② 信任钩子:已经服务 {数量} 位 {城市} 客户。点下面直接在 WhatsApp 问价,真人回复。\n'
        + '③ 场景钩子:{产品} 在当地怎么用 —— 实拍 30 秒看完就懂,想要直接聊。',
    creative: '以本地实拍为主:产品在当地街景 / 家里的真实使用画面、本地人出镜口播、'
            + '货到付款开箱。不要用一眼就能看出是批量 AI 生成的塑料感视频,东非用户对本地感很敏感。'
            + '竖版 9:16 为主,前 3 秒必须出现产品和价格。',
    status: '草稿',
    note: '广告户用客户自己的 BM 和支付卡,我们只做投放配置和优化。'
        + '中间页放隐私政策和服务条款,不要把广告直接指向最终成交页。',
  },
  {
    project: '【模板】东非本地服务 · 留资',
    vertical: '其他',
    objective: '线索 Leads',
    channel: '落地页 Landing',
    market: '坦桑尼亚 / 肯尼亚 · 城市区域,英语 + 斯瓦希里语',
    audience: '有明确服务需求的本地用户(装修、维修、培训、旅游、金融服务等),'
            + '按城市 + 宽泛兴趣起量。服务类决策比电商慢,给足学习期。',
    interests: 'Home Improvement, Local Services, Travel, Education, Small Business, '
             + 'Real Estate, Insurance, Financial Services',
    pacing: '目标选「潜在客户开发」,表单字段控制在 3 个以内(姓名 / 电话 / 需求),'
          + '多一个字段少一半线索。前 7 天只看单条线索成本,第二周开始看「线索 → 到店/成交」。'
          + '线索进来 30 分钟内必须有人跟进,超过 1 小时转化率掉一半以上。',
    welcome: '你好 👋 我们收到你的需求了。为了给你准确报价,'
           + '麻烦确认一下:{关键问题一} / {关键问题二}?回复后我马上安排。',
    copy: '① 直给:{服务} 在 {城市},上门报价免费,不满意不收费。\n'
        + '② 对比:自己折腾 {痛点},还不如找专业的。留个电话,今天就能排上。\n'
        + '③ 资质:持证 / 有保险 / 本地 {年数} 年,{数量} 单好评。留资看案例。',
    creative: '服务流程实拍(上门 → 施工/服务 → 完工),真实客户出镜说两句。'
            + '服务类靠信任,比产品类更需要真人真事,AI 口播只能做补充。',
    status: '草稿',
    note: '落地页必须挂隐私政策和服务条款,表单要写清楚收集什么、用来干嘛。'
        + '线索存进 CRM 做私域,复购和转介绍是服务类的主要利润来源。',
  },
  {
    project: '【模板】东南亚华人独立站 · 转化',
    vertical: '独立站/网购',
    objective: '转化 Conversions',
    channel: '多渠道',
    market: '马来西亚 / 新加坡 / 印尼华人圈 · 中文为主,英文为辅',
    audience: '25–50 岁华人消费者,习惯中文内容、熟悉本地电商与支付。'
            + 'Meta 跑宽泛 + 再营销,TikTok 跑兴趣标签,Google 跑品牌词和品类搜索词。'
            + '三个平台的人群不一样,素材不要直接互抄。',
    interests: '网购, 跨境电商, Shopee, Lazada, 时尚, 母婴, 健康养生, 家居生活, 美妆',
    pacing: '目标选「转化」,优化事件选「购买」;日均购买少于 15 单时先优化「加入购物车」,'
          + '等数据量够了再切购买。新品前 3 天别动,ROAS 低于 1.5 的组关掉,'
          + '高于 3 的组每天加 20% 预算。大促前 2 周先用再营销把人群池养起来。',
    welcome: '你好 👋 想了解哪一款?告诉我用途和预算,我推荐最合适的,'
           + '现在下单有 {优惠}。支持本地转账 / 货到付款。',
    copy: '① 利益点:{产品} 直邮到家,{优惠},不满意 7 天退。\n'
        + '② 痛点:还在为 {问题} 发愁?{产品} 这样解决,{数量} 位客户已经在用。\n'
        + '③ 社会证明:{平台} 热卖 {数量} 件,真实评价 {评分} 分。点进来看看。',
    creative: '中文口播 + 产品细节特写 + 真实买家评价截图。'
            + '华人市场对"价格 + 评价"最敏感,前 3 秒把优惠和销量打出来。'
            + '节日节点(双 11 / 农历新年 / 开斋节)提前两周备素材。',
    status: '草稿',
    note: 'Pixel 和转化 API 双上,iOS 掉数据严重。'
        + '广告户走客户自有,我们只负责配置和优化。',
  },
];

const uuid = () => crypto.randomUUID();

(async () => {
  const pool = mysql.createPool({
    host: process.env.DB_HOST || '127.0.0.1',
    user: process.env.DB_USER || 'runadops',
    password: process.env.DB_PASS || '',
    database: process.env.DB_NAME || 'runadops',
    charset: 'utf8mb4_general_ci',
  });

  try {
    await pool.query('SELECT 1');
  } catch (e) {
    console.error('连不上 MySQL:', e.message);
    process.exit(1);
  }

  // 找一个 owner 当作者,没有就留空
  const [owners] = await pool.query(
    "SELECT id FROM profiles WHERE role='owner' ORDER BY created_at LIMIT 1");
  const by = owners.length ? owners[0].id : null;

  const [rows] = await pool.query("SELECT type, data FROM records WHERE type IN ('package','brief')");
  const have = new Set(rows.map(r => {
    const d = typeof r.data === 'string' ? JSON.parse(r.data) : r.data;
    return r.type + ':' + (d.name || d.project || '');
  }));

  let added = 0, skipped = 0;
  for (const [type, list, key] of [['package', PACKAGES, 'name'], ['brief', BRIEFS, 'project']]) {
    for (const data of list) {
      if (have.has(type + ':' + data[key])) { skipped++; console.log('  跳过(已存在):', data[key]); continue; }
      await pool.query('INSERT INTO records (id,type,data,updated_by) VALUES (?,?,CAST(? AS JSON),?)',
        [uuid(), type, JSON.stringify(data), by]);
      added++;
      console.log('  已添加:', data[key]);
    }
  }

  const [[{ n: nPkg }]] = await pool.query("SELECT COUNT(*) n FROM records WHERE type='package'");
  const [[{ n: nBrief }]] = await pool.query("SELECT COUNT(*) n FROM records WHERE type='brief'");
  console.log(`\n新增 ${added} 条,跳过 ${skipped} 条。现在:套餐 ${nPkg} 个,投放配置 ${nBrief} 份。`);
  console.log('去控制台 Ctrl+F5 刷新就能看到,内容直接在界面上改。');
  await pool.end();
})();
