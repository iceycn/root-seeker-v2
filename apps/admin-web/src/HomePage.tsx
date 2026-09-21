import {
  BookOutlined,
  GithubOutlined,
  MailOutlined,
  RocketOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { Button, Card, ConfigProvider, Space, Spin, Tag, Timeline, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { api } from './App.tsx'

const GITHUB_URL = 'https://github.com/iceycn/root-seeker-v2'
const GITEE_URL = 'https://gitee.com/icey_1/root-seeker-v2'

const techGroups = [
  {
    title: '运行时',
    items: ['Python 3.11+', 'FastAPI', 'Pydantic', 'MCP Gateway', 'Skill Playbook'],
  },
  {
    title: '控制台',
    items: ['React 19', 'Ant Design', 'Vite', 'TypeScript'],
  },
  {
    title: '检索与存储',
    items: ['Zoekt 词法检索', 'Qdrant 语义检索', 'GitNexus 知识图谱', 'SQLite / MySQL'],
  },
  {
    title: '部署与触达',
    items: ['Docker Compose', '阿里云 ACR', '飞书 / 钉钉 / 企微 / Slack'],
  },
]

const changelog = [
  {
    version: 'v1.3.2',
    title: '登录后进入宣传首页',
    desc: '登录成功后首先进入宣传页：项目介绍、技术选型、联系信息与更新日志以卡片展示。',
  },
  {
    version: 'v1.3.1',
    title: 'ACR 双推修复',
    desc: '修复 GitHub Publish 向个人版阿里云 ACR 推送时被 OCI provenance 拒绝的问题。',
  },
  {
    version: 'v1.3.0',
    title: '国内预构建镜像',
    desc: '一键安装优先拉取阿里云 ACR；Publish 同时打 tag 到 Docker Hub 与 ACR。',
  },
  {
    version: 'v1.2.1',
    title: '消息模板说明',
    desc: '条件块写法改为与可用变量一致的表格，避免 {{#var}} / {{/var}} 难以理解。',
  },
  {
    version: 'v1.2.0',
    title: '登录与用户管理',
    desc: 'Admin 增加首次引导、Cookie 会话登录与用户管理，保护控制台与 API。',
  },
]

export default function HomePage() {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    void api<{ authenticated: boolean }>('/api/auth/status')
      .then((status) => {
        if (!status.authenticated) {
          window.location.replace('/login')
          return
        }
        setReady(true)
      })
      .catch(() => {
        window.location.replace('/login')
      })
  }, [])

  const logout = async () => {
    await api('/api/auth/logout', { method: 'POST' })
    window.location.href = '/login'
  }

  if (!ready) {
    return (
      <ConfigProvider theme={{ token: { colorPrimary: '#e85d75', borderRadius: 12 } }}>
        <div className="home-page" style={{ display: 'grid', placeItems: 'center' }}>
          <Spin size="large" />
        </div>
      </ConfigProvider>
    )
  }

  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#e85d75', borderRadius: 12 } }}>
      <div className="home-page">
        <header className="home-nav">
          <div className="brand">
            <span className="brand-icon">R</span>
            <span>RootSeeker</span>
            <Tag color="magenta">v1.3.2</Tag>
          </div>
          <Space>
            <Button href="/overview" type="primary">
              进入控制台
            </Button>
            <Button onClick={() => void logout()}>退出</Button>
          </Space>
        </header>

        <section className="home-hero">
          <Typography.Title level={1} className="home-hero-title">
            AI 驱动的内网故障排查与根因发现
          </Typography.Title>
          <Typography.Paragraph className="home-hero-desc">
            从一条告警或报错出发，自动还原现场、检索私有代码与知识图谱、汇聚证据，并产出可落地的根因报告。
            代码与日志可不出内网。
          </Typography.Paragraph>
        </section>

        <div className="home-cards">
          <Card
            className="home-card"
            title={
              <span>
                <RocketOutlined /> 项目介绍
              </span>
            }
          >
            <Typography.Paragraph>
              RootSeeker V2 是面向公司内网的排障平台。全链路覆盖：告警接入 → 日志 / 链路采集 → 代码检索与图谱 →
              根因分析 → 多渠道通知。Skill 可编排、MCP 可审计、Case 可回放；支持私有化部署。
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary">
              当前阶段：MVP 主链路已在开发环境端到端跑通；登录后首先进入宣传首页，再进入控制台。
            </Typography.Paragraph>
            <Space wrap>
              <Button type="primary" href={GITHUB_URL} target="_blank" rel="noreferrer" icon={<GithubOutlined />}>
                GitHub
              </Button>
              <Button href={GITEE_URL} target="_blank" rel="noreferrer">
                码云 Gitee
              </Button>
            </Space>
          </Card>

          <Card
            className="home-card"
            title={
              <span>
                <ToolOutlined /> 技术选型
              </span>
            }
          >
            {techGroups.map((group) => (
              <div key={group.title} className="home-tech-group">
                <Typography.Text strong>{group.title}</Typography.Text>
                <div className="home-tech-tags">
                  {group.items.map((item) => (
                    <Tag key={item}>{item}</Tag>
                  ))}
                </div>
              </div>
            ))}
          </Card>

          <Card
            className="home-card"
            title={
              <span>
                <MailOutlined /> 联系信息
              </span>
            }
          >
            <Typography.Paragraph>
              维护者：<Typography.Text strong>iceycn / RootSeeker Team</Typography.Text>
            </Typography.Paragraph>
            <Typography.Paragraph>
              问题与建议请在仓库提 Issue，欢迎 Star 与 PR。
            </Typography.Paragraph>
            <ul className="home-contact-list">
              <li>
                GitHub Issues：{' '}
                <Typography.Link href={`${GITHUB_URL}/issues`} target="_blank" rel="noreferrer">
                  iceycn/root-seeker-v2
                </Typography.Link>
              </li>
              <li>
                码云 Issues：{' '}
                <Typography.Link href={`${GITEE_URL}/issues`} target="_blank" rel="noreferrer">
                  icey_1/root-seeker-v2
                </Typography.Link>
              </li>
              <li>许可证：MIT License © 2026</li>
            </ul>
          </Card>

          <Card
            className="home-card"
            title={
              <span>
                <BookOutlined /> 更新日志
              </span>
            }
          >
            <Timeline
              items={changelog.map((item) => ({
                children: (
                  <div>
                    <Typography.Text strong>
                      {item.version} · {item.title}
                    </Typography.Text>
                    <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                      {item.desc}
                    </Typography.Paragraph>
                  </div>
                ),
              }))}
            />
          </Card>
        </div>

        <footer className="home-footer">MIT License © 2026 iceycn / RootSeeker Team</footer>
      </div>
    </ConfigProvider>
  )
}
