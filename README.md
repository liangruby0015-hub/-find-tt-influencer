# 潮玩 TikTok 博主追踪 Bot

自动抓取 TikTok 美区潮玩内容（盲盒、labubu、泡泡玛特等），将博主信息同步到 Google Sheet，并通过飞书推送热门视频日报。

## 功能

- **飞书日报**：每天 09:00 自动推送 TikTok 热门视频 + 热门话题到飞书群
- **博主同步**：每 4 小时抓取 50 条美区视频，提取博主信息（粉丝数、邮箱、简介、近月均播、视频风格）写入 Google Sheet
- **触达追踪**：同步博主时实时查询 Gmail 已发送邮件，直接写入准确的触达状态
- **发邮件（手动）**：按粉丝数范围和近月均播筛选未触达博主，预览确认后手动发送个性化品牌合作邀请邮件，自动更新触达状态

## 前置准备

部署前需要自行申请以下内容：

### 1. RapidAPI Key（TikTok 数据源）
1. 注册 [RapidAPI](https://rapidapi.com)
2. 搜索并订阅 **tiktok-scraper7**（有免费额度）
3. 在 API 页面复制 `X-RapidAPI-Key`

### 2. 飞书 Webhook
1. 打开飞书群 → 设置 → 机器人 → 添加自定义机器人
2. 复制 Webhook 地址
3. 多个群用英文逗号分隔

### 3. Google Sheet + 服务账号（博主表格）
1. 新建一个 Google Sheet，复制表格 ID（URL 中 `/d/` 后面的部分）
2. 打开 [Google Cloud Console](https://console.cloud.google.com)，新建项目
3. 启用 **Google Sheets API** 和 **Google Drive API**
4. 创建服务账号 → 下载 JSON 密钥 → 重命名为 `google_credentials.json`
5. 将服务账号邮箱（形如 `xxx@xxx.iam.gserviceaccount.com`）加为表格编辑者

### 4. Gmail OAuth 凭证（触达追踪）
1. 在同一个 Google Cloud 项目中启用 **Gmail API**
2. 创建 OAuth 客户端 ID（类型选「桌面应用」）→ 下载 JSON → 重命名为 `gmail_credentials.json`
3. 在 OAuth 同意屏幕的「测试用户」中添加你自己的 Gmail 地址

### 5. SMTP 邮件发送配置
1. 开启邮箱的 SMTP 服务并获取授权密码
   - **Gmail**：开启两步验证 → 前往 [应用专用密码](https://myaccount.google.com/apppasswords) 生成 16 位密码
   - **QQ邮箱**：设置 → 账户 → 开启 SMTP → 生成授权码
   - **163邮箱**：设置 → POP3/SMTP → 开启 → 设置授权密码
2. 填入 `.env` 的 `SMTP_USER` 和 `SMTP_PASSWORD`，端口推荐使用 `465`

## 安装

```bash
git clone https://github.com/liangruby0015-hub/-find-tt-influencer.git
cd -find-tt-influencer
pip3 install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入你的配置：

```
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
RAPIDAPI_KEY=你的RapidAPI Key
GOOGLE_SHEET_ID=你的Google Sheet ID

# 邮件签名
SENDER_NAME=你的姓名
BRAND_NAME=你的品牌名称
REPLY_EMAIL=你的邮箱地址

# Gmail SMTP 发信（开启两步验证后生成应用专用密码）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=你的邮箱地址
SMTP_PASSWORD=应用专用密码
```

将以下凭证文件放到项目根目录：
- `google_credentials.json`（服务账号密钥，联系项目负责人获取）
- `gmail_credentials.json`（Gmail OAuth 凭证，联系项目负责人获取）
- `gmail_token.json`（首次运行 `python3 main.py --sync-creators` 后自动生成，无需提供）

> `.env` 及以上凭证文件均不含在代码仓库中，请联系项目负责人私下获取。

## 首次运行

首次运行需要完成 Gmail 浏览器授权（之后自动缓存，无需重复）：

```bash
python3 main.py --sync-creators
```

浏览器会弹出 Google 授权页面，选择你的 Gmail 账号并点击「允许」，授权完成后程序自动继续。

## 运行

```bash
# 手动触发
python3 main.py --feishu          # 立即推送飞书日报
python3 main.py --sync-creators   # 立即同步博主到 Google Sheet（含实时触达校验）

# 发送合作邀请邮件（手动触发，发前先预览确认）
python3 main.py --send-emails --min-followers 5000 --max-followers 200000 --min-avg-plays 1000 --dry-run  # 预览名单和邮件内容
python3 main.py --send-emails --min-followers 5000 --max-followers 200000 --min-avg-plays 1000            # 确认后正式发送
python3 main.py --test-email 你的邮箱                                                                      # 发一封测试邮件给自己

# 启动定时任务（长期运行，不含发邮件）
python3 main.py
```

## 定时任务

| 任务 | 时间 |
|------|------|
| 飞书日报 | 每天 09:00 |
| 博主同步 → Google Sheet | 每 4 小时 |

## Google Sheet 字段说明

| 字段 | 说明 |
|------|------|
| TikTok账号 | 博主用户名 |
| 昵称 | 显示名称 |
| 粉丝数 | 当前粉丝数 |
| 获赞数 | 累计获赞 |
| 邮箱 | 从简介中提取的邮箱 |
| 简介 | TikTok 个人简介 |
| Instagram | ins_id |
| Twitter | twitter_id |
| 主页链接 | TikTok 主页 URL |
| 来源话题 | 通过哪个话题发现的 |
| 发现时间 | 写入日期 |
| 近月均播 | 最近 30 天视频平均播放量 |
| 视频风格 | 内容风格分析（开箱测评 / 收藏展示 等） |
| 是否触达 | 同步时实时查 Gmail 自动填入；否 / 已发送 / 邮箱重复请核查 |
| 备注 | 手动填写 |

## 文件说明

```
├── main.py              # 入口，定时任务调度
├── tiktok_scraper.py    # TikTok 数据抓取
├── creator_tracker.py   # 博主信息同步到 Google Sheet
├── feishu_sender.py     # 飞书消息推送
├── gmail_checker.py     # Gmail 已发送邮件查询
├── email_sender.py      # 博主合作邀请邮件发送
├── email_template.txt   # 邮件模板（直接编辑修改内容，支持 {{name}} 等变量）
├── .env.example         # 环境变量模板
└── requirements.txt     # Python 依赖
```
