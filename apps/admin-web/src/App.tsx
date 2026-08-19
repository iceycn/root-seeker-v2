import {
  ApiOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  HeartOutlined,
  KeyOutlined,
  MessageOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  App as AntApp,
  Badge,
  Button,
  Card,
  Checkbox,
  ConfigProvider,
  Divider,
  Empty,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tabs,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { MenuProps } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

type ApiRecord = Record<string, unknown>

type AiProvider = {
  name: string
  provider_type: string
  base_url?: string
  api_key?: string
  model?: string
  embedding_model?: string
  embedding_dimension?: number
  enabled?: boolean
  builtin?: boolean
  api_key_url?: string
  metadata?: {
    display_name?: string
    models?: string[]
    disabled_models?: string[]
    protocol?: string
    reasoning_enabled?: boolean
  }
}

type StatusData = ApiRecord & {
  skills_total?: number
  plugins_total?: number
  repos?: { total?: number }
  index?: { total?: number }
}

type SkillRecord = ApiRecord & {
  slug: string
  name?: string
  description?: string
  skill_kind?: string
  bound_tools?: string[]
  tags?: string[]
  triggers?: string[]
  required_tools?: string[]
  steps?: ApiRecord[]
  version?: string
  source_kind?: string
  role?: string
  enabled?: boolean
  is_default?: boolean
  env?: string[]
  metadata?: ApiRecord
}

type SkillReference = {
  path: string
  title?: string
  content: string
}

type SkillContent = ApiRecord & {
  slug: string
  source_kind?: string
  skill_md?: string
  rootseeker_skill_yaml?: string
  references?: SkillReference[]
  runtime_spec?: SkillRecord
  tool_parameters?: ToolParameterDoc[]
}

type JsonSchemaProperty = {
  type?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  items?: JsonSchemaProperty
}

type JsonSchema = {
  type?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

type ToolParameterDoc = {
  tool_name: string
  description?: string
  parameters_schema?: JsonSchema
  registered?: boolean
}

type PluginRecord = ApiRecord & {
  plugin_id: string
  display_name?: string
  kind?: string
}

type ToolRecord = ApiRecord & {
  name: string
  scope?: string
  server_name?: string
  description?: string
  parameters_schema?: JsonSchema
}

type RepoRecord = ApiRecord & {
  name: string
  url?: string
  local_path?: string
  default_branch?: string
  sync_status?: { state?: string; error_message?: string | null }
  metadata?: ApiRecord
}

type RemoteRepoRecord = ApiRecord & {
  provider: string
  name: string
  full_name: string
  clone_url?: string
  ssh_url?: string
  web_url?: string
  default_branch?: string
  private?: boolean
  imported?: boolean
  reimportable?: boolean
  registered_name?: string
  sync_state?: string
}

type RepoRemoteRecord = ApiRecord & {
  name: string
  provider: string
  base_url: string
  owner?: string
  git_username?: string
  api_path?: string
  has_token?: boolean
  masked_token?: string
}

type CatalogRecord = ApiRecord & {
  tenant: string
  environment: string
  service_name: string
  display_name?: string
  owner_team?: string
  language?: string
}

type NotificationChannelRecord = ApiRecord & {
  channel_id: string
  name: string
  channel_type?: string
  endpoint_url?: string
  enabled?: boolean
  has_secret?: boolean
  masked_secret?: string
  sort_order?: number
}

type McpServerRecord = ApiRecord & {
  server_id: string
  name: string
  transport?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  cwd?: string
  enabled?: boolean
  tools?: ApiRecord[]
  timeout_seconds?: number
  last_sync_at?: string
  last_error?: string
  has_env?: boolean
  tools_count?: number
  tool_names?: string[]
  discovery_status?: 'pending' | 'discovering' | 'ready' | 'failed'
}

type CronJobState = {
  status?: string
  next_run_at?: string | null
  last_started_at?: string | null
  last_finished_at?: string | null
  last_success_at?: string | null
  last_error?: string | null
  run_count?: number
}

type CronJobRecord = ApiRecord & {
  job_id: string
  name: string
  handler: string
  schedule: string
  timezone?: string
  enabled?: boolean
  builtin?: boolean
  deletable?: boolean
  notes?: string
  metadata?: ApiRecord
  state?: CronJobState | null
}

type CronJobRunRecord = ApiRecord & {
  job_id: string
  status: string
  started_at?: string
  finished_at?: string
  message?: string
  payload?: ApiRecord
}

type EnvVarRecord = ApiRecord & {
  key: string
  value?: string
  masked_value?: string
  scope?: string
  secret?: boolean
}

type ErrorChatCase = ApiRecord & {
  case_id?: string
  title?: string
  status?: string
  service_name?: string
  steps?: ApiRecord[]
}

type ErrorChatEvidence = ApiRecord & {
  item_id: string
  type?: string
  source?: string
  content?: ApiRecord
  collected_at?: string
}

type ErrorChatResult = ApiRecord & {
  id?: string
  content: string
  created_at?: string
  request?: ApiRecord
  case?: ErrorChatCase
  flow_run_id?: string
  evidence_count?: number
  evidence_summary?: string
  evidence_items?: ErrorChatEvidence[]
  flow_elapsed_ms?: number
  report?: ApiRecord & {
    root_cause?: { title?: string }
  }
  ai_analysis?: {
    ok?: boolean
    pending?: boolean
    provider?: string
    model?: string
    elapsed_ms?: number
    reason?: string
    error?: string
    content?: string
  }
  tool_results?: unknown[]
}

const api = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await response.text()
  let data: { detail?: unknown } | null = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!response.ok) {
    const detail = data?.detail
    let message = text || response.statusText
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg?: string }).msg)
          return JSON.stringify(item)
        })
        .join('; ')
    }
    throw new Error(message)
  }
  return (data ?? null) as T
}

const maskKey = (key?: string) => {
  if (!key) return '未设置'
  if (key.length <= 8) return `${key.slice(0, 2)}******`
  return `${key.slice(0, 3)}******${key.slice(-4)}`
}

type SchemaPropertyRow = {
  name: string
  type: string
  required: boolean
  description: string
}

const schemaPropertyRows = (schema?: JsonSchema): SchemaPropertyRow[] => {
  const properties = schema?.properties || {}
  const required = new Set(schema?.required || [])
  return Object.entries(properties).map(([name, meta]) => ({
    name,
    type: meta?.type || 'any',
    required: required.has(name),
    description: meta?.description || '',
  }))
}

const parameterSchemaColumns = [
  { title: '字段', dataIndex: 'name', width: 140 },
  { title: '类型', dataIndex: 'type', width: 90, render: (value: string) => <Tag>{value}</Tag> },
  { title: '必填', dataIndex: 'required', width: 60, render: (value: boolean) => (value ? '是' : '否') },
  { title: '说明', dataIndex: 'description' },
]

function renderEllipsisCell(value?: string | null) {
  const text = value?.trim() || '-'
  return (
    <Tooltip title={text}>
      <span className="table-cell-ellipsis">{text}</span>
    </Tooltip>
  )
}

const repoSyncStateLabels: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '待同步' },
  syncing: { color: 'processing', text: '同步中' },
  indexing: { color: 'processing', text: '索引中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

function canImportRemoteRepo(record: RemoteRepoRecord) {
  return !record.imported || record.reimportable || record.sync_state === 'failed'
}

function mergeRemoteRepoImportStatus(record: RemoteRepoRecord, registeredRepos: RepoRecord[]): RemoteRepoRecord {
  const registryName = record.registered_name || record.full_name.replace(/[/:]+/g, '__')
  const matched = registeredRepos.find(
    (repo) =>
      repo.name === registryName ||
      String(repo.metadata?.full_name || '') === record.full_name,
  )
  if (!matched) {
    return record
  }
  const sync_state = matched.sync_status?.state || record.sync_state
  return {
    ...record,
    imported: true,
    registered_name: matched.name,
    sync_state,
    reimportable: sync_state === 'failed',
  }
}

function renderRemoteRepoImportStatus(record: RemoteRepoRecord) {
  if (!record.imported) {
    return <Tag>未导入</Tag>
  }
  const state = record.sync_state || 'pending'
  const item = repoSyncStateLabels[state] || { color: 'default', text: state }
  return (
    <Space size={4} wrap>
      <Tag color="blue">已导入</Tag>
      <Tag color={item.color}>{item.text}</Tag>
      {record.reimportable || record.sync_state === 'failed' ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>可重新导入</Typography.Text>
      ) : null}
    </Space>
  )
}

const responsiveTableProps = {
  tableLayout: 'fixed' as const,
  style: { width: '100%' },
}

function ParameterSchemaTable({ schema }: { schema?: JsonSchema }) {
  const rows = schemaPropertyRows(schema)
  if (!rows.length) {
    return <Typography.Text type="secondary">无结构化参数定义</Typography.Text>
  }
  return (
    <Table
      size="small"
      pagination={false}
      rowKey="name"
      dataSource={rows}
      columns={parameterSchemaColumns}
    />
  )
}

function ToolParametersPanel({
  toolParameters,
  loading,
}: {
  toolParameters?: ToolParameterDoc[]
  loading?: boolean
}) {
  if (loading) {
    return null
  }
  if (!toolParameters?.length) {
    return <Empty description="暂无关联工具参数" />
  }
  return (
    <Tabs
      items={toolParameters.map((doc) => ({
        key: doc.tool_name,
        label: doc.tool_name,
        children: (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {doc.description ? (
              <Typography.Paragraph style={{ marginBottom: 0 }}>{doc.description}</Typography.Paragraph>
            ) : null}
            {doc.registered === false ? (
              <Typography.Text type="warning">工具未在 registry 注册</Typography.Text>
            ) : null}
            <ParameterSchemaTable schema={doc.parameters_schema} />
          </Space>
        ),
      }))}
    />
  )
}

const providerDisplay = (provider: AiProvider) =>
  provider.metadata?.display_name || provider.name

const repoRemoteDefaultBaseUrl: Record<string, string> = {
  github: 'https://github.com',
  gitee: 'https://gitee.com',
  yunxiao: 'https://openapi-rdc.aliyuncs.com',
  custom: '',
  generic: '',
}

const MCP_SERVER_JSON_TEMPLATE = {
  plantuml: {
    command: 'npx',
    args: ['-y', 'plantuml-mcp-server'],
    env: {
      PLANTUML_SERVER_URL: 'https://www.plantuml.com/plantuml',
    },
  },
}

const MCP_SERVER_JSON_EMPTY = {
  name: 'my-server',
  transport: 'stdio',
  command: '',
  args: [],
  env: {},
  timeout_seconds: 120,
}

type McpServerPayload = {
  name: string
  transport: string
  command: string
  args: string[]
  env: Record<string, string>
  cwd: string
  enabled: boolean
  timeout_seconds: number
}

const isMcpServerBlock = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === 'object' && typeof (value as Record<string, unknown>).command === 'string')

const normalizeMcpServerBlock = (name: string, block: Record<string, unknown>): McpServerPayload => {
  const command = String(block.command || '').trim()
  if (!command) {
    throw new Error('command 必填')
  }
  const args = Array.isArray(block.args) ? block.args.map((item) => String(item)) : []
  const envSource = block.env
  const env: Record<string, string> = {}
  if (envSource && typeof envSource === 'object') {
    for (const [key, value] of Object.entries(envSource as Record<string, unknown>)) {
      env[String(key)] = String(value ?? '')
    }
  }
  return {
    name: String(block.name || name).trim(),
    transport: String(block.transport || 'stdio'),
    command,
    args,
    env,
    cwd: String(block.cwd || ''),
    enabled: block.enabled !== false,
    timeout_seconds: Number(block.timeout_seconds || 120),
  }
}

const normalizeMcpServerConfig = (parsed: unknown): McpServerPayload => {
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('JSON 必须是对象')
  }
  const root = parsed as Record<string, unknown>

  if (root.mcpServers && typeof root.mcpServers === 'object') {
    const servers = root.mcpServers as Record<string, unknown>
    const keys = Object.keys(servers)
    if (keys.length !== 1) {
      throw new Error('mcpServers 中请只包含一个 Server，或分多次添加')
    }
    const name = keys[0]
    const block = servers[name]
    if (!isMcpServerBlock(block)) {
      throw new Error(`无法解析 mcpServers.${name}`)
    }
    return normalizeMcpServerBlock(name, block)
  }

  const keys = Object.keys(root)
  if (keys.length === 1 && !isMcpServerBlock(root)) {
    const name = keys[0]
    const block = root[name]
    if (isMcpServerBlock(block)) {
      return normalizeMcpServerBlock(name, block)
    }
  }

  if (typeof (root as { name?: unknown }).name === 'string' || isMcpServerBlock(root)) {
    const name =
      typeof (root as { name?: unknown }).name === 'string'
        ? String((root as { name: string }).name)
        : 'mcp-server'
    return normalizeMcpServerBlock(name, root)
  }

  throw new Error('无法识别的 MCP JSON 格式')
}

const mcpServerRecordToJson = (record: McpServerRecord) =>
  JSON.stringify(
    {
      name: record.name,
      transport: record.transport || 'stdio',
      command: record.command,
      args: record.args || [],
      env: record.env || {},
      cwd: record.cwd || '',
      enabled: record.enabled !== false,
      timeout_seconds: record.timeout_seconds || 120,
    },
    null,
    2,
  )

const getMcpServerToolNames = (record: McpServerRecord) =>
  record.tool_names ||
  (record.tools || []).map((tool) => String(tool.name || '')).filter(Boolean)

const renderMcpServerToolsTooltip = (record: McpServerRecord) => {
  const tools = (record.tools || []) as ApiRecord[]
  const names = getMcpServerToolNames(record)
  if (!names.length) {
    return '暂无可用工具，请点击「同步工具」'
  }
  if (tools.length) {
    return (
      <div style={{ maxWidth: 420 }}>
        {tools.map((tool) => {
          const name = String(tool.name || '')
          if (!name) return null
          const description = String(tool.description || '').trim()
          return (
            <div key={name} style={{ marginBottom: 6 }}>
              <Typography.Text strong style={{ color: '#fff' }}>{name}</Typography.Text>
              {description ? (
                <Typography.Text style={{ color: 'rgba(255,255,255,0.85)' }}> — {description}</Typography.Text>
              ) : null}
              <br />
              <Typography.Text style={{ color: 'rgba(255,255,255,0.72)', fontSize: 12 }}>
                ext.{record.server_id}.{name}
              </Typography.Text>
            </div>
          )
        })}
      </div>
    )
  }
  return names.join('、')
}

const renderAllMcpToolsTooltip = (servers: McpServerRecord[]) => {
  const sections = servers
    .map((server) => {
      const names = getMcpServerToolNames(server)
      if (!names.length) return null
      return { name: server.name, names }
    })
    .filter(Boolean) as { name: string; names: string[] }[]
  if (!sections.length) {
    return '暂无可用工具'
  }
  return (
    <div style={{ maxWidth: 420 }}>
      {sections.map((section) => (
        <div key={section.name} style={{ marginBottom: 8 }}>
          <Typography.Text strong style={{ color: '#fff' }}>{section.name}</Typography.Text>
          <Typography.Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            ：{section.names.join('、')}
          </Typography.Text>
        </div>
      ))}
    </div>
  )
}

const mcpDiscoveryStatusMeta = (record: McpServerRecord) => {
  const status = record.discovery_status || ((record.tools_count ?? (record.tools || []).length) > 0 ? 'ready' : 'pending')
  switch (status) {
    case 'discovering':
      return { color: 'processing' as const, text: '发现中' }
    case 'ready':
      return { color: 'success' as const, text: '已接入' }
    case 'failed':
      return { color: 'error' as const, text: '接入失败' }
    default:
      return { color: 'default' as const, text: '待发现' }
  }
}

const pathToView: Record<string, string> = {
  '/': 'models',
  '/admin': 'models',
  '/models': 'models',
  '/advanced-settings': 'advanced',
  '/skills': 'skills',
  '/repos': 'repos',
  '/catalog': 'catalog',
  '/plugins': 'plugins',
  '/mcp-servers': 'mcpServers',
  '/notification-channels': 'notificationChannels',
  '/schedules': 'schedules',
  '/semantic-search': 'semantic',
  '/error-chat': 'errorChat',
  '/overview': 'overview',
}

const viewToPath: Record<string, string> = {
  models: '/models',
  advanced: '/advanced-settings',
  skills: '/skills',
  repos: '/repos',
  catalog: '/catalog',
  plugins: '/plugins',
  mcpServers: '/mcp-servers',
  notificationChannels: '/notification-channels',
  schedules: '/schedules',
  semantic: '/semantic-search',
  errorChat: '/error-chat',
  overview: '/overview',
}

function App() {
  const [active, setActive] = useState(() => pathToView[window.location.pathname] || 'models')
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [defaultProvider, setDefaultProvider] = useState<string | null>(null)
  const [defaultModel, setDefaultModel] = useState<string | null>(null)
  const [statusData, setStatusData] = useState<StatusData | null>(null)
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [skillEditorOpen, setSkillEditorOpen] = useState(false)
  const [skillEditorLoading, setSkillEditorLoading] = useState(false)
  const [skillEditorReadOnly, setSkillEditorReadOnly] = useState(false)
  const [skillSpecText, setSkillSpecText] = useState('')
  const [selectedSkillContent, setSelectedSkillContent] = useState<SkillContent | null>(null)
  const [selectedSkill, setSelectedSkill] = useState<SkillRecord | null>(null)
  const [plugins, setPlugins] = useState<PluginRecord[]>([])
  const [tools, setTools] = useState<ToolRecord[]>([])
  const [repos, setRepos] = useState<RepoRecord[]>([])
  const [repoRemotes, setRepoRemotes] = useState<RepoRemoteRecord[]>([])
  const [remoteRepos, setRemoteRepos] = useState<RemoteRepoRecord[]>([])
  const [selectedRemoteRepoKeys, setSelectedRemoteRepoKeys] = useState<string[]>([])
  const [catalogItems, setCatalogItems] = useState<CatalogRecord[]>([])
  const [notificationChannels, setNotificationChannels] = useState<NotificationChannelRecord[]>([])
  const [mcpServers, setMcpServers] = useState<McpServerRecord[]>([])
  const [mcpToolsTotal, setMcpToolsTotal] = useState(0)
  const [broadcastEnabled, setBroadcastEnabled] = useState(true)
  const [cronJobs, setCronJobs] = useState<CronJobRecord[]>([])
  const [cronHandlers, setCronHandlers] = useState<string[]>([])
  const [cronModalOpen, setCronModalOpen] = useState(false)
  const [editingCronJob, setEditingCronJob] = useState<CronJobRecord | null>(null)
  const [cronRunsOpen, setCronRunsOpen] = useState(false)
  const [cronRuns, setCronRuns] = useState<CronJobRunRecord[]>([])
  const [cronRunsJobId, setCronRunsJobId] = useState<string | null>(null)
  const [settingsData, setSettingsData] = useState<Record<string, unknown>>({})
  const [envVars, setEnvVars] = useState<EnvVarRecord[]>([])
  const [providerModalOpen, setProviderModalOpen] = useState(false)
  const [repoRemoteModalOpen, setRepoRemoteModalOpen] = useState(false)
  const [envModalOpen, setEnvModalOpen] = useState(false)
  const [runtimeModalOpen, setRuntimeModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<AiProvider | null>(null)
  const [editingRepoRemote, setEditingRepoRemote] = useState<RepoRemoteRecord | null>(null)
  const [editingRuntimeKey, setEditingRuntimeKey] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [disabledModels, setDisabledModels] = useState<string[]>([])
  const [form] = Form.useForm()
  const [repoForm] = Form.useForm()
  const [repoRemoteForm] = Form.useForm()
  const [remoteRepoForm] = Form.useForm()
  const repoRemoteProvider = Form.useWatch('provider', repoRemoteForm)
  const selectedRemoteName = Form.useWatch('remote_name', remoteRepoForm)
  const selectedRemoteProvider = repoRemotes.find((item) => item.name === selectedRemoteName)?.provider
  const [localRepoForm] = Form.useForm()
  const [catalogForm] = Form.useForm()
  const [channelForm] = Form.useForm()
  const [channelModalOpen, setChannelModalOpen] = useState(false)
  const [editingChannel, setEditingChannel] = useState<NotificationChannelRecord | null>(null)
  const [mcpServerModalOpen, setMcpServerModalOpen] = useState(false)
  const [editingMcpServer, setEditingMcpServer] = useState<McpServerRecord | null>(null)
  const [mcpServerJsonText, setMcpServerJsonText] = useState('')
  const [mcpServerSaving, setMcpServerSaving] = useState(false)
  const [cronForm] = Form.useForm()
  const [skillForm] = Form.useForm()
  const [semanticForm] = Form.useForm()
  const [errorCaseForm] = Form.useForm()
  const [envForm] = Form.useForm()
  const [runtimeForm] = Form.useForm()
  const [semanticResult, setSemanticResult] = useState<unknown>(null)
  const [errorChatItems, setErrorChatItems] = useState<ErrorChatResult[]>([])
  const [errorChatInput, setErrorChatInput] = useState('')
  const [historyCollapsed, setHistoryCollapsed] = useState(false)
  const [errorChatSubmitting, setErrorChatSubmitting] = useState(false)
  const [errorChatResult, setErrorChatResult] = useState<ErrorChatResult | null>(null)
  const [apiMessage, contextHolder] = message.useMessage()

  const navigateTo = (view: string) => {
    setActive(view)
    const path = viewToPath[view] || '/models'
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }
  }

  const pageMeta: Record<string, { title: string; desc: string }> = {
    overview: { title: '总览状态', desc: '系统健康、索引、服务目录和运行时资源概览。' },
    semantic: { title: '语义搜索', desc: '使用 Qdrant 在已索引代码块里做语义搜索。' },
    errorChat: { title: '错误排查助手', desc: '提交错误信息、日志或现象，形成可追踪的排查历史。' },
    skills: { title: 'Skills 管理', desc: 'Flow Skill 编排排查链路；Tool Skill 描述各工具如何取参与协作。' },
    plugins: { title: 'Plugins / Tools', desc: '查看已加载插件和 MCP 工具注册情况。' },
    mcpServers: {
      title: 'MCP 协议',
      desc: '粘贴 Cursor / Claude 风格的 MCP JSON（如 plantuml 配置），保存后自动发现工具并注册到 McpGateway。',
    },
    repos: { title: 'Repo 管理', desc: '注册仓库、同步代码并触发 Zoekt/Qdrant 索引。' },
    catalog: { title: 'Service Catalog', desc: '配置 service_name 到仓库、日志源、负责人等信息的映射。' },
    models: { title: '大语言模型', desc: '系统会根据用户内容智能选择最合适的模型，您也可以切换默认模型。' },
    notificationChannels: { title: '通知渠道', desc: '配置分析结论出站通知；启用多个渠道后，报告生成时自动广播。' },
    schedules: { title: '定时任务', desc: '管理仓库增量同步等定时任务：启停、改调度、立即执行与运行记录。' },
    advanced: { title: '高级设置', desc: '管理 Skill/MCP 运行时环境变量与 RootSeeker 运行时配置。' },
  }

  const loadProviders = useCallback(async () => {
    const data = await api<{ items: AiProvider[]; default_provider: string | null; default_model?: string | null }>('/api/ai-providers')
    setProviders(data.items)
    setDefaultProvider(data.default_provider)
    setDefaultModel(data.default_model || null)
  }, [])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      loadProviders().catch((error) => apiMessage.error(String(error)))
    }, 0)
    const onPopState = () => setActive(pathToView[window.location.pathname] || 'models')
    window.addEventListener('popstate', onPopState)
    return () => {
      window.clearTimeout(loadTimer)
      window.removeEventListener('popstate', onPopState)
    }
  }, [apiMessage, loadProviders])

  useEffect(() => {
    if (active === 'overview') api<StatusData>('/api/status').then(setStatusData).catch((e) => apiMessage.error(String(e)))
    if (active === 'skills') api<{ items: SkillRecord[] }>('/api/skills').then((d) => setSkills(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'plugins') {
      api<{ items: PluginRecord[] }>('/api/plugins').then((d) => setPlugins(d.items || [])).catch((e) => apiMessage.error(String(e)))
      api<{ items: ToolRecord[] }>('/api/tools').then((d) => setTools(d.items || [])).catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'repos') {
      api<{ repos: RepoRecord[] }>('/api/repos').then((d) => setRepos(d.repos || [])).catch((e) => apiMessage.error(String(e)))
      api<{ items: RepoRemoteRecord[] }>('/api/repo-remotes').then((d) => {
        const items = d.items || []
        setRepoRemotes(items)
        if (items.length) {
          const current = remoteRepoForm.getFieldValue('remote_name')
          if (!current) {
            remoteRepoForm.setFieldsValue({
              remote_name: items[0].name,
              owner: items[0].owner || '',
            })
          }
        }
      }).catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'catalog') api<{ items: CatalogRecord[] }>('/api/catalog').then((d) => setCatalogItems(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'mcpServers') {
      api<{ items: McpServerRecord[]; tools_total?: number }>('/api/mcp-servers')
        .then((d) => {
          setMcpServers(d.items || [])
          setMcpToolsTotal(Number(d.tools_total || 0))
        })
        .catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'notificationChannels') {
      api<{ items: NotificationChannelRecord[] }>('/api/notification-channels')
        .then((d) => setNotificationChannels(d.items || []))
        .catch((e) => apiMessage.error(String(e)))
      api<{ settings: { broadcast_enabled?: boolean } }>('/api/notification-channel-settings')
        .then((d) => setBroadcastEnabled(d.settings?.broadcast_enabled !== false))
        .catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'schedules') {
      api<{ items: CronJobRecord[]; handlers?: string[] }>('/api/cron-jobs')
        .then((d) => {
          setCronJobs(d.items || [])
          setCronHandlers(d.handlers || [])
        })
        .catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'errorChat') api<{ items: ErrorChatResult[] }>('/api/error-chat').then((d) => setErrorChatItems(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'advanced') {
      api<{ settings: Record<string, unknown> }>('/api/settings').then((d) => {
        setSettingsData(d.settings || {})
        runtimeForm.setFieldsValue(d.settings || {})
      }).catch((e) => apiMessage.error(String(e)))
      api<{ items: EnvVarRecord[] }>('/api/env-vars').then((d) => setEnvVars(d.items || [])).catch((e) => apiMessage.error(String(e)))
    }
  }, [active, apiMessage, runtimeForm])

  const builtinProviders = useMemo(
    () => providers.filter((provider) => provider.builtin && !provider.api_key),
    [providers],
  )
  const customProviders = useMemo(
    () => providers.filter((provider) => !provider.builtin || provider.api_key),
    [providers],
  )

  const openProviderModal = (provider?: AiProvider) => {
    setEditingProvider(provider || null)
    const presetModels = provider?.metadata?.models || (provider?.model ? [provider.model] : [])
    setModels(presetModels)
    setDisabledModels(provider?.metadata?.disabled_models || [])
    form.setFieldsValue({
      name: provider?.name || '',
      display_name: providerDisplay(provider || ({ name: '' } as AiProvider)),
      base_url: provider?.base_url || '',
      api_key: '',
      provider_type: provider?.provider_type || 'openai_compatible',
      reasoning_enabled: provider?.metadata?.reasoning_enabled ?? provider?.name === 'deepseek',
    })
    setProviderModalOpen(true)
  }

  const saveProvider = async () => {
    const values = await form.validateFields()
    await api('/api/ai-providers', {
      method: 'POST',
      body: JSON.stringify({
        name: values.name,
        provider_type: values.provider_type,
        base_url: values.base_url || '',
        api_key: values.api_key || editingProvider?.api_key || '',
        model: models[0] || '',
        embedding_model: '',
        embedding_dimension: 1536,
        enabled: true,
        metadata: {
          display_name: values.display_name,
          protocol: values.provider_type,
          models,
          disabled_models: disabledModels,
          reasoning_enabled: Boolean(values.reasoning_enabled),
        },
      }),
    })
    apiMessage.success('提供商已保存')
    setProviderModalOpen(false)
    await loadProviders()
  }

  const testProvider = async (provider: AiProvider) => {
    const hide = apiMessage.loading(`正在测试 ${providerDisplay(provider)}...`, 0)
    try {
      const result = await api<{ ok: boolean; response_ms?: number; status_code?: number; error?: string }>(
        `/api/ai-providers/${encodeURIComponent(provider.name)}/test`,
        { method: 'POST' },
      )
      hide()
      if (result.ok) {
        apiMessage.success(`${providerDisplay(provider)} 连接正常，响应 ${result.response_ms ?? '-'}ms`)
      } else {
        apiMessage.error(`测试失败：${result.error || result.status_code || 'unknown'}`)
      }
    } catch (error) {
      hide()
      apiMessage.error(`测试失败：${String(error)}`)
    }
  }

  const switchModel = async (provider: AiProvider, model: string) => {
    await api(`/api/ai-providers/${encodeURIComponent(provider.name)}/models/${encodeURIComponent(model)}/switch`, {
      method: 'POST',
    })
    apiMessage.success(`已切换到 ${providerDisplay(provider)} / ${model}`)
    await loadProviders()
  }

  const deleteProvider = async (provider: AiProvider) => {
    await api(`/api/ai-providers/${encodeURIComponent(provider.name)}`, { method: 'DELETE' })
    apiMessage.success('已删除提供商')
    await loadProviders()
  }

  const refreshRepos = async () => {
    const data = await api<{ repos: RepoRecord[] }>('/api/repos')
    setRepos(data.repos || [])
  }

  const refreshRepoRemotes = async () => {
    const data = await api<{ items: RepoRemoteRecord[] }>('/api/repo-remotes')
    setRepoRemotes(data.items || [])
  }

  const openRepoRemoteModal = (remote?: RepoRemoteRecord) => {
    setEditingRepoRemote(remote || null)
    setRepoRemoteModalOpen(true)
    repoRemoteForm.setFieldsValue(
      remote
        ? { ...remote, token: '' }
        : { provider: 'github', base_url: repoRemoteDefaultBaseUrl.github },
    )
  }

  const saveRepoRemote = async () => {
    const values = await repoRemoteForm.validateFields()
    await api('/api/repo-remotes', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('远端源已保存')
    setRepoRemoteModalOpen(false)
    setEditingRepoRemote(null)
    repoRemoteForm.resetFields()
    await refreshRepoRemotes()
  }

  const deleteRepoRemote = async (name: string) => {
    await api(`/api/repo-remotes/${encodeURIComponent(name)}`, { method: 'DELETE' })
    apiMessage.success('远端源已删除')
    await refreshRepoRemotes()
  }

  const registerRepo = async () => {
    const values = await repoForm.validateFields()
    await api('/api/repos', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('仓库已注册')
    await refreshRepos()
  }

  const discoverRemoteRepos = async () => {
    try {
      const values = await remoteRepoForm.validateFields()
      const payload = { ...values }
      setRemoteRepos([])
      const data = await api<{ repos: RemoteRepoRecord[] }>('/api/repos/discover', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setRemoteRepos(data.repos || [])
      setSelectedRemoteRepoKeys([])
      apiMessage.success(`发现 ${data.repos?.length || 0} 个仓库`)
    } catch (error) {
      apiMessage.error(String(error))
    }
  }

  const importRemoteRepoRecords = async (selected: RemoteRepoRecord[]) => {
    try {
      const values = await remoteRepoForm.validateFields()
      const remote = repoRemotes.find((item) => item.name === values.remote_name)
      const pending = selected.filter((repo) => canImportRemoteRepo(repo))
      if (!pending.length) {
        apiMessage.warning('所选仓库均已导入且状态正常')
        return
      }
      let reimportCount = 0
      for (const repo of pending) {
        const reimport = Boolean(repo.imported && (repo.reimportable || repo.sync_state === 'failed'))
        const name = repo.registered_name || repo.full_name.replace(/[/:]+/g, '__')
        if (reimport) {
          reimportCount += 1
        }
        await api('/api/repos', {
          method: 'POST',
          body: JSON.stringify({
            name,
            url: repo.clone_url || repo.ssh_url || repo.web_url,
            branch: repo.default_branch || 'main',
            metadata: {
              source: 'remote',
              provider: repo.provider || remote?.provider,
              full_name: repo.full_name,
              remote_name: remote?.name || values.remote_name,
              remote_base_url: remote?.base_url,
              git_username: remote?.git_username,
              web_url: repo.web_url,
            },
          }),
        })
        if (values.trigger_sync) {
          await api(`/api/repos/${encodeURIComponent(name)}/sync`, {
            method: 'POST',
            body: JSON.stringify({ trigger_index: true, force_reclone: reimport }),
          })
        }
      }
      const importedFullNames = new Set(pending.map((repo) => repo.full_name))
      setRemoteRepos((prev) =>
        prev.map((repo) => {
          if (!importedFullNames.has(repo.full_name)) {
            return repo
          }
          return {
            ...repo,
            imported: true,
            reimportable: false,
            registered_name: repo.registered_name || repo.full_name.replace(/[/:]+/g, '__'),
            sync_state: values.trigger_sync ? 'syncing' : 'pending',
          }
        }),
      )
      setSelectedRemoteRepoKeys((prev) => prev.filter((key) => !importedFullNames.has(String(key))))
      apiMessage.success(reimportCount > 0 ? `已重新导入 ${pending.length} 个仓库` : `已导入 ${pending.length} 个仓库`)
      await refreshRepos()
    } catch (error) {
      await refreshRepos()
      apiMessage.error(String(error))
    }
  }

  const importSelectedRemoteRepos = async () => {
    const merged = remoteRepos.map((record) => mergeRemoteRepoImportStatus(record, repos))
    await importRemoteRepoRecords(merged.filter((repo) => selectedRemoteRepoKeys.includes(repo.full_name)))
  }

  const importLocalRepo = async () => {
    const values = await localRepoForm.validateFields()
    await api('/api/repos/import-local', {
      method: 'POST',
      body: JSON.stringify(values),
    })
    apiMessage.success('本地仓库已导入')
    await refreshRepos()
  }

  const syncRepo = async (name: string) => {
    try {
      const result = await api<{ ok?: boolean; message?: string }>(`/api/repos/${encodeURIComponent(name)}/sync`, {
        method: 'POST',
        body: JSON.stringify({ trigger_index: true }),
      })
      if (result.ok === false) {
        throw new Error(result.message || '仓库同步/索引失败')
      }
      apiMessage.success('仓库同步/索引已完成')
      await refreshRepos()
    } catch (error) {
      apiMessage.error(String(error))
      await refreshRepos()
    }
  }

  const deleteRepo = async (name: string) => {
    await api(`/api/repos/${encodeURIComponent(name)}`, { method: 'DELETE' })
    apiMessage.success('仓库已删除')
    await refreshRepos()
  }

  const refreshCatalog = async () => {
    const data = await api<{ items: CatalogRecord[] }>('/api/catalog')
    setCatalogItems(data.items || [])
  }

  const saveCatalog = async () => {
    const values = await catalogForm.validateFields()
    await api('/api/catalog', {
      method: 'POST',
      body: JSON.stringify({
        ...values,
        repositories: values.repositories ? JSON.parse(values.repositories) : [],
      }),
    })
    apiMessage.success('服务目录已保存')
    await refreshCatalog()
  }

  const deleteCatalog = async (record: CatalogRecord) => {
    await api(`/api/catalog/${record.tenant}/${record.environment}/${encodeURIComponent(record.service_name)}`, { method: 'DELETE' })
    apiMessage.success('服务已删除')
    await refreshCatalog()
  }

  const refreshNotificationChannels = async () => {
    const data = await api<{ items: NotificationChannelRecord[] }>('/api/notification-channels')
    setNotificationChannels(data.items || [])
    const settings = await api<{ settings: { broadcast_enabled?: boolean } }>('/api/notification-channel-settings')
    setBroadcastEnabled(settings.settings?.broadcast_enabled !== false)
  }

  const openChannelModal = (record?: NotificationChannelRecord) => {
    setEditingChannel(record || null)
    channelForm.setFieldsValue(
      record
        ? { ...record, secret: '' }
        : { channel_type: 'webhook', enabled: true },
    )
    setChannelModalOpen(true)
  }

  const saveNotificationChannel = async () => {
    const values = await channelForm.validateFields()
    if (editingChannel?.channel_id) {
      await api(`/api/notification-channels/${encodeURIComponent(editingChannel.channel_id)}`, {
        method: 'PUT',
        body: JSON.stringify(values),
      })
      apiMessage.success('通知渠道已更新')
    } else {
      await api('/api/notification-channels', { method: 'POST', body: JSON.stringify(values) })
      apiMessage.success('通知渠道已创建')
    }
    setChannelModalOpen(false)
    setEditingChannel(null)
    channelForm.resetFields()
    await refreshNotificationChannels()
  }

  const toggleNotificationChannel = async (record: NotificationChannelRecord, enabled: boolean) => {
    await api(`/api/notification-channels/${encodeURIComponent(record.channel_id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    })
    await refreshNotificationChannels()
  }

  const testNotificationChannel = async (channelId: string) => {
    const data = await api<{ ok: boolean; error?: string }>(
      `/api/notification-channels/${encodeURIComponent(channelId)}/test`,
      { method: 'POST' },
    )
    if (data.ok) apiMessage.success('通知渠道测试成功')
    else apiMessage.error(`通知渠道测试失败：${data.error || 'unknown'}`)
  }

  const deleteNotificationChannel = async (channelId: string) => {
    await api(`/api/notification-channels/${encodeURIComponent(channelId)}`, { method: 'DELETE' })
    apiMessage.success('通知渠道已删除')
    await refreshNotificationChannels()
  }

  const refreshMcpServers = async () => {
    const data = await api<{ items: McpServerRecord[]; tools_total?: number }>('/api/mcp-servers')
    setMcpServers(data.items || [])
    setMcpToolsTotal(Number(data.tools_total || 0))
  }

  useEffect(() => {
    if (active !== 'mcpServers') return
    const hasDiscovering = mcpServers.some((item) => item.discovery_status === 'discovering')
    if (!hasDiscovering) return
    const timer = window.setInterval(() => {
      refreshMcpServers().catch((error) => apiMessage.error(String(error)))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [active, mcpServers, apiMessage])

  const openMcpServerModal = (record?: McpServerRecord) => {
    if (record) {
      setEditingMcpServer(record)
      setMcpServerJsonText(mcpServerRecordToJson(record))
    } else {
      setEditingMcpServer(null)
      setMcpServerJsonText(JSON.stringify(MCP_SERVER_JSON_EMPTY, null, 2))
    }
    setMcpServerModalOpen(true)
  }

  const saveMcpServer = async () => {
    setMcpServerSaving(true)
    try {
      let parsed: unknown
      try {
        parsed = JSON.parse(mcpServerJsonText)
      } catch {
        apiMessage.error('JSON 格式错误，请检查语法')
        return
      }
      let payload: McpServerPayload
      try {
        payload = normalizeMcpServerConfig(parsed)
      } catch (error) {
        apiMessage.error(String(error))
        return
      }
      if (payload.command.toLowerCase() === 'npx' && !payload.args.includes('-y')) {
        payload.args = ['-y', ...payload.args]
      }
      if (editingMcpServer?.server_id) {
        const data = await api<{ ok: boolean; async?: boolean }>(
          `/api/mcp-servers/${encodeURIComponent(editingMcpServer.server_id)}`,
          {
            method: 'PUT',
            body: JSON.stringify(payload),
          },
        )
        apiMessage.success(
          data.async ? 'MCP Server 已更新，正在后台发现工具（可在列表查看状态）' : 'MCP Server 已更新',
        )
      } else {
        await api<{ ok: boolean }>('/api/mcp-servers', { method: 'POST', body: JSON.stringify(payload) })
        apiMessage.success('MCP Server 已添加，正在后台发现工具（可在列表查看状态）')
      }
      setMcpServerModalOpen(false)
      setEditingMcpServer(null)
      setMcpServerJsonText('')
      await refreshMcpServers()
      if (active === 'plugins') {
        const toolsData = await api<{ items: ToolRecord[] }>('/api/tools')
        setTools(toolsData.items || [])
      }
    } catch (error) {
      apiMessage.error(`保存失败：${String(error)}`)
      throw error
    } finally {
      setMcpServerSaving(false)
    }
  }

  const testMcpServer = async (serverId: string) => {
    const data = await api<{ ok: boolean; tools?: ApiRecord[]; probe?: ApiRecord }>(
      `/api/mcp-servers/${encodeURIComponent(serverId)}/test`,
      { method: 'POST' },
    )
    const names = (data.tools || [])
      .map((tool) => String(tool.name || ''))
      .filter(Boolean)
    const count = names.length
    apiMessage.success(
      count > 0
        ? `连接成功，发现 ${count} 个工具：${names.join(', ')}`
        : '连接成功，但未发现可用工具',
    )
  }

  const syncMcpServerTools = async (serverId: string) => {
    await api<{ ok: boolean }>(
      `/api/mcp-servers/${encodeURIComponent(serverId)}/sync-tools`,
      { method: 'POST' },
    )
    apiMessage.success('已提交后台同步，请在列表查看状态')
    await refreshMcpServers()
  }

  const deleteMcpServer = async (serverId: string) => {
    await api(`/api/mcp-servers/${encodeURIComponent(serverId)}`, { method: 'DELETE' })
    apiMessage.success('MCP Server 已删除')
    if (editingMcpServer?.server_id === serverId) {
      setMcpServerModalOpen(false)
      setEditingMcpServer(null)
      setMcpServerJsonText('')
    } else if (!mcpServerModalOpen) {
      setEditingMcpServer(null)
      setMcpServerJsonText('')
    }
    await refreshMcpServers()
  }

  const toggleMcpServer = async (record: McpServerRecord, enabled: boolean) => {
    await api(`/api/mcp-servers/${encodeURIComponent(record.server_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
    await refreshMcpServers()
  }

  const updateBroadcastEnabled = async (enabled: boolean) => {
    await api('/api/notification-channel-settings', {
      method: 'PUT',
      body: JSON.stringify({ broadcast_enabled: enabled }),
    })
    setBroadcastEnabled(enabled)
    apiMessage.success(enabled ? '已启用全局广播' : '已关闭全局广播')
  }

  const refreshCronJobs = async () => {
    const data = await api<{ items: CronJobRecord[]; handlers?: string[] }>('/api/cron-jobs')
    setCronJobs(data.items || [])
    setCronHandlers(data.handlers || [])
  }

  const openCronModal = (job?: CronJobRecord) => {
    setEditingCronJob(job || null)
    if (job) {
      cronForm.setFieldsValue({
        name: job.name,
        handler: job.handler,
        schedule: job.schedule,
        timezone: job.timezone || 'UTC',
        enabled: job.enabled !== false,
        notes: job.notes || '',
      })
    } else {
      cronForm.setFieldsValue({
        name: '',
        handler: cronHandlers[0] || 'repo.sync_changed',
        schedule: '@hourly',
        timezone: 'UTC',
        enabled: true,
        notes: '',
      })
    }
    setCronModalOpen(true)
  }

  const saveCronJob = async () => {
    const values = await cronForm.validateFields()
    if (editingCronJob) {
      await api(`/api/cron-jobs/${encodeURIComponent(editingCronJob.job_id)}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: values.name,
          schedule: values.schedule,
          timezone: values.timezone,
          enabled: values.enabled,
          notes: values.notes || '',
          handler: editingCronJob.builtin ? undefined : values.handler,
        }),
      })
      apiMessage.success('定时任务已更新')
    } else {
      await api('/api/cron-jobs', {
        method: 'POST',
        body: JSON.stringify(values),
      })
      apiMessage.success('定时任务已创建')
    }
    setCronModalOpen(false)
    await refreshCronJobs()
  }

  const toggleCronJob = async (job: CronJobRecord, enabled: boolean) => {
    await api(`/api/cron-jobs/${encodeURIComponent(job.job_id)}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    })
    apiMessage.success(enabled ? '已启用' : '已停用')
    await refreshCronJobs()
  }

  const deleteCronJob = async (jobId: string) => {
    await api(`/api/cron-jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
    apiMessage.success('定时任务已删除')
    await refreshCronJobs()
  }

  const runCronJob = async (jobId: string) => {
    const data = await api<{
      ok: boolean
      started?: boolean
      result?: { message?: string; status?: string }
    }>(`/api/cron-jobs/${encodeURIComponent(jobId)}/run`, { method: 'POST' })
    if (data.started) apiMessage.success(data.result?.message || '已开始执行')
    else if (data.result?.status === 'skipped') apiMessage.warning(data.result?.message || '任务已跳过')
    else if (data.ok) apiMessage.success(data.result?.message || '任务已执行成功')
    else apiMessage.error(`执行失败：${data.result?.message || data.result?.status || 'unknown'}`)
    await refreshCronJobs()
    if (cronRunsOpen && cronRunsJobId === jobId) {
      await openCronRuns(jobId)
    }
  }

  const openCronRuns = async (jobId: string) => {
    setCronRunsJobId(jobId)
    const data = await api<{ items: CronJobRunRecord[] }>(`/api/cron-jobs/${encodeURIComponent(jobId)}/runs`)
    setCronRuns(data.items || [])
    setCronRunsOpen(true)
  }

  const refreshSkills = async () => {
    const data = await api<{ items: SkillRecord[] }>('/api/skills')
    setSkills(data.items || [])
  }

  const installSkill = async () => {
    const values = await skillForm.validateFields()
    await api('/api/skills/install', {
      method: 'POST',
      body: JSON.stringify({ source: values.source, overwrite: Boolean(values.overwrite) }),
    })
    apiMessage.success('Skill 已安装')
    skillForm.resetFields()
    await refreshSkills()
  }

  const setDefaultSkill = async (record: SkillRecord) => {
    const name = record.name || record.slug
    await api(`/api/skills/${encodeURIComponent(name)}/default`, { method: 'POST' })
    apiMessage.success(`已设为默认：${name}`)
    await refreshSkills()
  }

  const disableSkill = async (record: SkillRecord) => {
    const name = record.name || record.slug
    await api(`/api/skills/${encodeURIComponent(name)}/disable`, { method: 'POST' })
    apiMessage.success(`已禁用：${name}`)
    await refreshSkills()
  }

  const enableSkill = async (record: SkillRecord) => {
    const name = record.name || record.slug
    await api(`/api/skills/${encodeURIComponent(name)}/enable`, { method: 'POST' })
    apiMessage.success(`已启用：${name}`)
    await refreshSkills()
  }

  const openSkillEditor = async (record: SkillRecord, readOnly = false) => {
    setSelectedSkill(record)
    setSelectedSkillContent(null)
    setSkillSpecText('')
    setSkillEditorReadOnly(readOnly)
    setSkillEditorOpen(true)
    setSkillEditorLoading(true)
    try {
      if (readOnly) {
        const detail = await api<SkillContent>(`/api/skills/${encodeURIComponent(record.slug)}/content`)
        setSelectedSkillContent(detail)
        if (detail.runtime_spec) setSelectedSkill(detail.runtime_spec)
        setSkillSpecText(detail.skill_md || '')
      } else {
        const detail = await api<SkillRecord>(`/api/skills/${encodeURIComponent(record.slug)}`)
        setSelectedSkill(detail)
        setSkillSpecText(JSON.stringify(detail, null, 2))
      }
    } finally {
      setSkillEditorLoading(false)
    }
  }

  const saveSkillSpec = async () => {
    if (skillEditorReadOnly) return
    let spec: SkillRecord
    try {
      spec = JSON.parse(skillSpecText) as SkillRecord
    } catch {
      apiMessage.error('SkillSpec JSON 格式不正确')
      return
    }
    if (!spec.slug || !spec.name) {
      apiMessage.error('SkillSpec 必须包含 name 和 slug')
      return
    }
    setSkillEditorLoading(true)
    try {
      await api('/api/skills', { method: 'PUT', body: JSON.stringify({ spec }) })
      apiMessage.success('Skill 已更新')
      setSkillEditorOpen(false)
      await refreshSkills()
    } finally {
      setSkillEditorLoading(false)
    }
  }

  const deleteSkill = async (record: SkillRecord) => {
    Modal.confirm({
      title: `删除 Skill：${record.slug}`,
      content: '删除后会从当前运行时和管理端配置中移除。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await api(`/api/skills/${encodeURIComponent(record.slug)}`, { method: 'DELETE' })
        apiMessage.success('Skill 已删除')
        await refreshSkills()
      },
    })
  }

  const runSemanticSearch = async () => {
    const values = await semanticForm.validateFields()
    const data = await api('/api/code/semantic-search', { method: 'POST', body: JSON.stringify(values) })
    setSemanticResult(data)
  }

  const pollErrorChatAnalysis = (itemId: string, attempt = 0) => {
    if (attempt >= 30) return
    window.setTimeout(() => {
      api<{ items: ErrorChatResult[] }>('/api/error-chat')
        .then((data) => {
          const items = data.items || []
          setErrorChatItems(items)
          const updated = items.find((item) => item.id === itemId)
          if (!updated) return
          setErrorChatResult((current) => (current?.id === itemId ? updated : current))
          if (updated.ai_analysis?.pending) pollErrorChatAnalysis(itemId, attempt + 1)
        })
        .catch((error) => apiMessage.error(String(error)))
    }, 2000)
  }

  const submitErrorChat = async () => {
    const formValues = await errorCaseForm.validateFields()
    const content = errorChatInput.trim()
    if (!content) {
      apiMessage.warning('请输入错误信息')
      return
    }
    setErrorChatSubmitting(true)
    try {
      const payload: Record<string, unknown> = {
        content,
        environment: formValues.environment || 'prod',
        severity: formValues.severity || 'error',
      }
      const serviceName = String(formValues.service_name || '').trim()
      if (serviceName) payload.service_name = serviceName
      const traceId = String(formValues.trace_id || '').trim()
      if (traceId) payload.trace_id = traceId
      const data = await api<{ item: ErrorChatResult }>('/api/error-chat', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setErrorChatItems((items) => [...items, data.item])
      setErrorChatResult(data.item)
      setErrorChatInput('')
      apiMessage.success('排查流程已完成')
      if (data.item.id && data.item.ai_analysis?.pending) pollErrorChatAnalysis(data.item.id)
    } finally {
      setErrorChatSubmitting(false)
    }
  }

  const clearErrorChat = async () => {
    await api('/api/error-chat', { method: 'DELETE' })
    setErrorChatItems([])
    setErrorChatResult(null)
    apiMessage.success('历史记录已清空')
  }

  const refreshEnvVars = async () => {
    const data = await api<{ items: EnvVarRecord[] }>('/api/env-vars')
    setEnvVars(data.items || [])
  }

  const saveEnvVar = async () => {
    const values = await envForm.validateFields()
    await api('/api/env-vars', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('环境变量已保存')
    envForm.resetFields()
    setEnvModalOpen(false)
    await refreshEnvVars()
  }

  const deleteEnvVar = async (key: string) => {
    await api(`/api/env-vars/${encodeURIComponent(key)}`, { method: 'DELETE' })
    apiMessage.success('环境变量已删除')
    await refreshEnvVars()
  }

  const saveRuntimeSettings = async () => {
    const values = await runtimeForm.validateFields()
    const settings = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== undefined && value !== ''),
    )
    await api('/api/settings', { method: 'PUT', body: JSON.stringify({ settings }) })
    apiMessage.success('运行时配置已保存')
    setSettingsData({ ...settingsData, ...settings })
    setRuntimeModalOpen(false)
    setEditingRuntimeKey(null)
  }

  const openEnvModal = (record?: EnvVarRecord) => {
    envForm.setFieldsValue(record || { scope: 'runtime', secret: false })
    setEnvModalOpen(true)
  }

  const openRuntimeModal = (key: string, value: unknown) => {
    setEditingRuntimeKey(key)
    runtimeForm.setFieldsValue({ [key]: value ?? '' })
    setRuntimeModalOpen(true)
  }

  const menuItems: MenuProps['items'] = [
    { key: 'sessions', label: '会话', type: 'group' },
    { key: 'overview', icon: <ThunderboltOutlined />, label: '总览状态' },
    { key: 'semantic', icon: <SearchOutlined />, label: '语义搜索' },
    { key: 'errorChat', icon: <MessageOutlined />, label: '错误排查' },
    { key: 'agent', label: '智能体', type: 'group' },
    { key: 'skills', icon: <ExperimentOutlined />, label: 'Skills 管理' },
    { key: 'plugins', icon: <ApiOutlined />, label: 'Plugins / Tools' },
    { key: 'mcpServers', icon: <ApiOutlined />, label: 'MCP 协议' },
    { key: 'repos', icon: <FolderOpenOutlined />, label: 'Repo 管理' },
    { key: 'catalog', icon: <HeartOutlined />, label: 'Service Catalog' },
    { key: 'settings', label: '设置', type: 'group' },
    { key: 'models', icon: <RobotOutlined />, label: '大模型' },
    { key: 'notificationChannels', icon: <MessageOutlined />, label: '通知渠道' },
    { key: 'schedules', icon: <ClockCircleOutlined />, label: '定时任务' },
    { key: 'advanced', icon: <SettingOutlined />, label: '高级设置' },
  ]

  const meta = pageMeta[active] || pageMeta.models

  const ProviderCard = ({ provider }: { provider: AiProvider }) => {
    const authorized = Boolean(provider.api_key)
    const modelsOfProvider = provider.metadata?.models || (provider.model ? [provider.model] : [])
    const modelCount = modelsOfProvider.length
    return (
      <Card
        className={`provider-card ${authorized ? 'authorized' : ''}`}
        bordered={false}
      >
        <div className="provider-header">
          <Space>
            <div className="provider-logo">{providerDisplay(provider).slice(0, 1).toUpperCase()}</div>
            <div>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {providerDisplay(provider)}
              </Typography.Title>
              <Typography.Text type="secondary">{provider.name}</Typography.Text>
            </div>
          </Space>
          <Badge status={authorized ? 'success' : 'default'} text={authorized ? '已授权' : '未授权'} />
        </div>
        <div className="provider-meta">
          <div><b>接入地址：</b>{provider.base_url || '未配置'}</div>
          <div><b>API 密钥：</b>{maskKey(provider.api_key)}</div>
          <div><b>模型：</b>{modelCount} 个模型</div>
        </div>
        <div className="provider-actions">
          {authorized ? (
            <Button type="link" icon={<ThunderboltOutlined />} onClick={() => testProvider(provider)}>测试连接</Button>
          ) : (
            <Button type="link" icon={<KeyOutlined />} onClick={() => window.open(provider.api_key_url || '#', '_blank')}>获取 API Key</Button>
          )}
          <Button type="link" icon={<EditOutlined />} onClick={() => openProviderModal(provider)}>设置</Button>
          {authorized && <Button type="link" danger icon={<DeleteOutlined />} onClick={() => deleteProvider(provider)}>删除提供商</Button>}
        </div>
      </Card>
    )
  }

  const PlaceholderPage = ({ title, description }: { title: string; description: string }) => (
    <Card bordered={false} className="model-pool">
      <div style={{ padding: 24 }}>
        <Typography.Title level={4}>{title}</Typography.Title>
        <Typography.Text type="secondary">{description}</Typography.Text>
      </div>
    </Card>
  )

  const renderContent = () => {
    if (active === 'models') {
      return (
        <>
          <Card className="model-pool" bordered={false}>
            <div className="model-pool-head">
              <div>
                <Typography.Title level={5}>可用模型池</Typography.Title>
                <Typography.Text type="secondary">以下模型可用于自动分析。标记的偏好模型在无法确定时优先使用。</Typography.Text>
              </div>
              <Tag color="green">
                {modelPoolProviders.reduce((sum, item) => sum + item.models.length, 0)} 个可用
              </Tag>
            </div>
            {modelPoolProviders.length ? modelPoolProviders.map(({ provider, models }) => (
              <div className="model-provider-group" key={`pool-${provider.name}`}>
                <div className="model-provider-title">
                  <span>{providerDisplay(provider)}</span>
                  <span>{models.length} 个</span>
                </div>
                {models.map((model) => (
                  <div className="model-row" key={`${provider.name}-${model}`}>
                    <Space>
                      <span className="star">☆</span>
                      <div>
                        <div className="model-name">{model}</div>
                        <Typography.Text type="secondary">{model}</Typography.Text>
                      </div>
                    </Space>
                    {defaultProvider === provider.name && defaultModel === model ? (
                      <Tag color="green">默认</Tag>
                    ) : (
                      <Button onClick={() => switchModel(provider, model)} size="small">切换</Button>
                    )}
                  </div>
                ))}
              </div>
            )) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用模型，请先为提供商配置 API Key" />
            )}
          </Card>

          <div className="section-title-row">
            <div>
              <Typography.Title level={4}>模型提供商</Typography.Title>
              <Typography.Text type="secondary">为每个模型提供商配置 API 密钥和接入端点。</Typography.Text>
            </div>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openProviderModal()}>添加提供商</Button>
          </div>

          <Typography.Title level={5}>自定义提供商</Typography.Title>
          <div className="provider-grid">
            {customProviders.length ? customProviders.map((provider) => <ProviderCard provider={provider} key={provider.name} />) : <Card className="provider-empty" bordered={false}><Empty description="暂无自定义提供商" /></Card>}
          </div>

          <Typography.Title level={5} style={{ marginTop: 24 }}>内置提供商</Typography.Title>
          <div className="provider-grid">
            {builtinProviders.map((provider) => <ProviderCard provider={provider} key={provider.name} />)}
          </div>
        </>
      )
    }
    if (active === 'overview') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div className="provider-grid">
            <Card bordered={false}><Typography.Text type="secondary">Skills</Typography.Text><Typography.Title level={2}>{statusData?.skills_total ?? '-'}</Typography.Title></Card>
            <Card bordered={false}><Typography.Text type="secondary">Plugins</Typography.Text><Typography.Title level={2}>{statusData?.plugins_total ?? '-'}</Typography.Title></Card>
            <Card bordered={false}><Typography.Text type="secondary">Repos</Typography.Text><Typography.Title level={2}>{statusData?.repos?.total ?? '-'}</Typography.Title></Card>
            <Card bordered={false}><Typography.Text type="secondary">Indexed Repos</Typography.Text><Typography.Title level={2}>{statusData?.index?.total ?? '-'}</Typography.Title></Card>
          </div>
          <Card title="状态详情" bordered={false}><pre>{JSON.stringify(statusData, null, 2)}</pre></Card>
        </Space>
      )
    }
    if (active === 'skills') {
      const systemSkills = skills.filter((skill) => skill.source_kind === 'builtin')
      const userSkills = skills.filter((skill) => skill.source_kind !== 'builtin')
      const flowSkills = systemSkills.filter((skill) => skill.skill_kind === 'flow' || (skill.steps?.length ?? 0) > 0)
      const toolSkills = systemSkills.filter((skill) => skill.skill_kind === 'tool' || skill.skill_kind === 'tool_group')
      const kindLabel = (kind?: string) => ({ flow: 'Flow', tool: 'Tool', tool_group: 'Tool 组' }[kind || ''] || kind || '-')
      const renderSkillDetails = (record: SkillRecord) => (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>{record.description || '暂无描述'}</Typography.Paragraph>
          <Space wrap>
            {(record.tags || []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          </Space>
          <Typography.Text type="secondary">类型：{kindLabel(record.skill_kind)} · 角色：{record.role || '-'}</Typography.Text>
          <Typography.Text type="secondary">状态：{record.enabled === false ? '已禁用' : '启用'}{record.is_default ? ' · 当前默认 playbook' : ''}</Typography.Text>
          <Typography.Text type="secondary">Allowed tools：{(record['allowed-tools'] as string[] | undefined || record.bound_tools || []).join(', ') || '-'}</Typography.Text>
          <Typography.Text type="secondary">Env keys：{(record.env || []).join(', ') || '-'}</Typography.Text>
          <Typography.Text type="secondary">Triggers：{(record.triggers || []).join(', ') || '-'}</Typography.Text>
          <Typography.Text type="secondary">Required Tools：{(record.required_tools || []).join(', ') || '-'}</Typography.Text>
          {(record.bound_tools?.length ?? 0) > 0 && (
            <Typography.Text type="secondary">Bound Tools：{(record.bound_tools || []).join(', ')}</Typography.Text>
          )}
          {(record.steps?.length ?? 0) > 0 ? (
            <Table
              size="small"
              pagination={false}
              rowKey={(step) => String(step.step_id || step.action)}
              dataSource={record.steps || []}
              columns={[
                { title: '步骤', dataIndex: 'name' },
                { title: 'Action', dataIndex: 'action' },
                { title: 'Tool Skill', dataIndex: 'tool_skill_slug' },
              ]}
            />
          ) : null}
        </Space>
      )
      const skillColumns = (readOnly: boolean) => [
        { title: 'Slug', dataIndex: 'slug' },
        { title: '名称', dataIndex: 'name' },
        { title: '类型', render: (_: unknown, record: SkillRecord) => kindLabel(record.skill_kind) },
        { title: '版本', dataIndex: 'version' },
        { title: '步骤/工具', render: (_: unknown, record: SkillRecord) => (
          record.skill_kind === 'flow' || (record.steps?.length ?? 0) > 0
            ? (record.steps?.length ?? 0)
            : (record.bound_tools || []).join(', ')
        ) },
        {
          title: '操作',
          render: (_: unknown, record: SkillRecord) => (
            <Space>
              <Button icon={<EyeOutlined />} onClick={() => openSkillEditor(record, true)}>
                查看
              </Button>
              <Button onClick={() => setDefaultSkill(record)}>设为默认</Button>
              {record.enabled === false
                ? <Button onClick={() => enableSkill(record)}>启用</Button>
                : <Button onClick={() => disableSkill(record)}>禁用</Button>}
              {record.source_kind !== 'builtin' && <Button danger icon={<DeleteOutlined />} onClick={() => deleteSkill(record)}>删除</Button>}
            </Space>
          ),
        },
      ]
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Tabs
            items={[
              {
                key: 'flow',
                label: `Flow Skills (${flowSkills.length})`,
                children: (
                  <Card bordered={false}>
                    <Table
                      rowKey="slug"
                      dataSource={flowSkills}
                      expandable={{ expandedRowRender: renderSkillDetails }}
                      columns={skillColumns(true)}
                    />
                  </Card>
                ),
              },
              {
                key: 'tool',
                label: `Tool Skills (${toolSkills.length})`,
                children: (
                  <Card bordered={false}>
                    <Table
                      rowKey="slug"
                      dataSource={toolSkills}
                      expandable={{ expandedRowRender: renderSkillDetails }}
                      columns={skillColumns(true)}
                    />
                  </Card>
                ),
              },
              {
                key: 'user',
                label: `用户 Skills (${userSkills.length})`,
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <Card title="安装 Skill" bordered={false}>
                      <Form form={skillForm} layout="inline">
                        <Form.Item name="source" rules={[{ required: true, message: '请填写本地路径或 Git URL' }]}>
                          <Input placeholder="本地路径或 Git URL" style={{ width: 360 }} />
                        </Form.Item>
                        <Form.Item name="overwrite" valuePropName="checked">
                          <Checkbox>覆盖已有</Checkbox>
                        </Form.Item>
                        <Form.Item><Button type="primary" onClick={installSkill}>安装</Button></Form.Item>
                      </Form>
                    </Card>
                    <Card bordered={false}>
                      <Table
                        rowKey="slug"
                        dataSource={userSkills}
                        expandable={{ expandedRowRender: renderSkillDetails }}
                        columns={skillColumns(false)}
                      />
                    </Card>
                  </Space>
                ),
              },
            ]}
          />
          <Modal
            title={selectedSkill ? `${skillEditorReadOnly ? 'SKILL.md' : 'Runtime SkillSpec'}：${selectedSkill.slug}` : 'Skill'}
            open={skillEditorOpen}
            onCancel={() => setSkillEditorOpen(false)}
            onOk={saveSkillSpec}
            okText={skillEditorReadOnly ? '关闭' : '保存'}
            cancelText="取消"
            confirmLoading={skillEditorLoading}
            footer={skillEditorReadOnly ? [
              <Button key="close" onClick={() => setSkillEditorOpen(false)}>关闭</Button>,
            ] : undefined}
            width={920}
          >
            <Spin spinning={skillEditorLoading} tip="正在加载 Skill 内容...">
              <div style={{ minHeight: skillEditorLoading ? 420 : undefined }}>
              {skillEditorReadOnly ? (
                <Tabs
                  items={[
                    {
                      key: 'skill-md',
                      label: 'SKILL.md',
                      children: (
                        <Input.TextArea
                          value={skillSpecText}
                          autoSize={{ minRows: 18, maxRows: 28 }}
                          readOnly
                          spellCheck={false}
                        />
                      ),
                    },
                    {
                      key: 'runtime',
                      label: '运行编排',
                      children: (
                        <Input.TextArea
                          value={
                            skillEditorLoading
                              ? ''
                              : selectedSkillContent?.rootseeker_skill_yaml
                                || (selectedSkillContent?.runtime_spec
                                  ? JSON.stringify(selectedSkillContent.runtime_spec, null, 2)
                                  : '')
                          }
                          autoSize={{ minRows: 18, maxRows: 28 }}
                          readOnly
                          spellCheck={false}
                        />
                      ),
                    },
                    {
                      key: 'references',
                      label: skillEditorLoading
                        ? '子技能说明'
                        : `子技能说明 (${selectedSkillContent?.references?.length || 0})`,
                      children: skillEditorLoading ? null : selectedSkillContent?.references?.length ? (
                        <Tabs
                          tabPosition="left"
                          items={(selectedSkillContent.references || []).map((ref) => ({
                            key: ref.path,
                            label: ref.path.replace('references/', '').replace('.md', ''),
                            children: (
                              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                <Typography.Text type="secondary">{ref.path}</Typography.Text>
                                <Input.TextArea
                                  value={ref.content}
                                  autoSize={{ minRows: 16, maxRows: 26 }}
                                  readOnly
                                  spellCheck={false}
                                />
                              </Space>
                            ),
                          }))}
                        />
                      ) : <Empty description="暂无子技能说明" />,
                    },
                    {
                      key: 'parameters',
                      label: skillEditorLoading
                        ? '参数说明'
                        : `参数说明 (${selectedSkillContent?.tool_parameters?.length || 0})`,
                      children: (
                        <ToolParametersPanel
                          loading={skillEditorLoading}
                          toolParameters={selectedSkillContent?.tool_parameters}
                        />
                      ),
                    },
                  ]}
                />
              ) : (
                <Input.TextArea
                  value={skillSpecText}
                  onChange={(event) => setSkillSpecText(event.target.value)}
                  autoSize={{ minRows: 18, maxRows: 28 }}
                  readOnly={skillEditorReadOnly}
                  spellCheck={false}
                />
              )}
              </div>
            </Spin>
          </Modal>
        </Space>
      )
    }
    if (active === 'plugins') {
      return (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Card title="Plugins" bordered={false}>
            <Table
              rowKey="plugin_id"
              dataSource={plugins}
              columns={[
                { title: 'ID', dataIndex: 'plugin_id' },
                { title: '名称', dataIndex: 'display_name' },
                { title: '类型', dataIndex: 'kind' },
              ]}
            />
          </Card>
          <Card title="Tools" bordered={false}>
            <Table
              rowKey="name"
              dataSource={tools}
              expandable={{
                expandedRowRender: (record: ToolRecord) => (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Typography.Paragraph style={{ marginBottom: 0 }}>
                      {record.description || '暂无描述'}
                    </Typography.Paragraph>
                    <ParameterSchemaTable schema={record.parameters_schema} />
                  </Space>
                ),
              }}
              columns={[
                { title: '名称', dataIndex: 'name' },
                { title: 'Scope', dataIndex: 'scope' },
                { title: 'Server', dataIndex: 'server_name' },
                {
                  title: '参数',
                  render: (_: unknown, record: ToolRecord) => {
                    const count = schemaPropertyRows(record.parameters_schema).length
                    return count ? <Tag>{count} 个字段</Tag> : <Typography.Text type="secondary">-</Typography.Text>
                  },
                },
              ]}
            />
          </Card>
        </Space>
      )
    }
    if (active === 'repos') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }} className="repo-page">
          <Tabs
            items={[
              {
                key: 'remote-sources',
                label: '远端源管理',
                children: (
                  <Card
                    title="远端源列表"
                    bordered={false}
                    className="admin-table-card"
                    extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openRepoRemoteModal()}>新增远端源</Button>}
                  >
                    <Table
                      {...responsiveTableProps}
                      rowKey="name"
                      dataSource={repoRemotes}
                      columns={[
                        { title: '名称', dataIndex: 'name', width: 120, ellipsis: true },
                        { title: '类型', dataIndex: 'provider', width: 90 },
                        { title: '域名', dataIndex: 'base_url', width: 180, ellipsis: true, render: renderEllipsisCell },
                        { title: '默认组织', dataIndex: 'owner', width: 160, ellipsis: true, render: renderEllipsisCell },
                        { title: '克隆账号', dataIndex: 'git_username', width: 120, ellipsis: true, render: renderEllipsisCell },
                        { title: 'API Path', dataIndex: 'api_path', width: 120, ellipsis: true, render: renderEllipsisCell },
                        { title: 'Token', width: 140, render: (_: unknown, r: RepoRemoteRecord) => r.has_token ? r.masked_token : '-' },
                        {
                          title: '操作',
                          width: 160,
                          render: (_: unknown, r: RepoRemoteRecord) => (
                            <Space>
                              <Button icon={<EditOutlined />} onClick={() => openRepoRemoteModal(r)}>编辑</Button>
                              <Button danger icon={<DeleteOutlined />} onClick={() => deleteRepoRemote(r.name)}>删除</Button>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Card>
                ),
              },
              {
                key: 'remote',
                label: '从远端导入',
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <Card title="从远端搜索并导入" bordered={false} className="repo-discover-card">
                      <Form form={remoteRepoForm} layout="inline" className="repo-discover-form" initialValues={{ per_page: 50, page: 1, trigger_sync: true }}>
                        <Form.Item name="remote_name" rules={[{ required: true }]}>
                          <Select
                            placeholder="选择远端源"
                            style={{ width: 220 }}
                            options={repoRemotes.map((remote) => ({ label: `${remote.name} (${remote.provider})`, value: remote.name }))}
                            onChange={(name) => {
                              const remote = repoRemotes.find((item) => item.name === name)
                              remoteRepoForm.setFieldValue('owner', remote?.owner || '')
                              setRemoteRepos([])
                              setSelectedRemoteRepoKeys([])
                            }}
                          />
                        </Form.Item>
                        <Form.Item name="query"><Input placeholder="搜索仓库名，可空" style={{ width: 220 }} /></Form.Item>
                        <Form.Item
                          name="owner"
                          label={
                            selectedRemoteProvider === 'yunxiao'
                              ? 'organizationId（中心版必填）'
                              : '覆盖组织 / Group'
                          }
                        >
                          <Input
                            placeholder={
                              selectedRemoteProvider === 'yunxiao'
                                ? '中心版填组织 ID；Region 版可留空'
                                : '覆盖组织/Group'
                            }
                            style={{ width: 220 }}
                          />
                        </Form.Item>
                        <Form.Item name="api_path"><Input placeholder="覆盖 API path" style={{ width: 180 }} /></Form.Item>
                        <Form.Item name="trigger_sync" valuePropName="checked"><Switch checkedChildren="导入后同步" unCheckedChildren="只注册" /></Form.Item>
                        <Form.Item><Button type="primary" icon={<SearchOutlined />} onClick={discoverRemoteRepos}>搜索</Button></Form.Item>
                        <Form.Item><Button icon={<FolderOpenOutlined />} onClick={importSelectedRemoteRepos}>导入选中</Button></Form.Item>
                      </Form>
                    </Card>
                    <Card title="远端仓库列表" bordered={false} className="admin-table-card">
                      <Table
                        {...responsiveTableProps}
                        rowKey="full_name"
                        dataSource={remoteRepos.map((record) => mergeRemoteRepoImportStatus(record, repos))}
                        rowSelection={{
                          selectedRowKeys: selectedRemoteRepoKeys,
                          onChange: (keys) => setSelectedRemoteRepoKeys(keys.map(String)),
                          getCheckboxProps: (record: RemoteRepoRecord) => ({
                            disabled: !canImportRemoteRepo(record),
                          }),
                        }}
                        columns={[
                          { title: '仓库', dataIndex: 'full_name', width: 280, ellipsis: true, render: renderEllipsisCell },
                          { title: 'Provider', dataIndex: 'provider', width: 100 },
                          { title: 'Clone URL', dataIndex: 'clone_url', ellipsis: true, render: renderEllipsisCell },
                          { title: '状态', width: 160, render: (_: unknown, record: RemoteRepoRecord) => renderRemoteRepoImportStatus(record) },
                          { title: '可见性', width: 90, render: (_: unknown, r: RemoteRepoRecord) => r.private ? <Tag color="red">private</Tag> : <Tag>public</Tag> },
                          {
                            title: '操作',
                            width: 100,
                            render: (_: unknown, r: RemoteRepoRecord) => {
                              if (!canImportRemoteRepo(r)) {
                                return <Button disabled>已导入</Button>
                              }
                              if (r.imported && (r.reimportable || r.sync_state === 'failed')) {
                                return <Button type="primary" danger onClick={() => importRemoteRepoRecords([r])}>重新导入</Button>
                              }
                              return <Button onClick={() => importRemoteRepoRecords([r])}>导入</Button>
                            },
                          },
                        ]}
                      />
                    </Card>
                  </Space>
                ),
              },
              {
                key: 'local',
                label: '本地仓库导入',
                children: (
                  <Card title="导入本地 Git 仓库" bordered={false}>
                    <Form form={localRepoForm} layout="inline" initialValues={{ branch: 'main', trigger_index: false }}>
                      <Form.Item name="path" rules={[{ required: true }]}><Input placeholder="/path/to/local/repo" style={{ width: 360 }} /></Form.Item>
                      <Form.Item name="name"><Input placeholder="名称，可空" style={{ width: 180 }} /></Form.Item>
                      <Form.Item name="branch"><Input placeholder="branch" style={{ width: 120 }} /></Form.Item>
                      <Form.Item name="trigger_index" valuePropName="checked"><Switch checkedChildren="立即索引" unCheckedChildren="只导入" /></Form.Item>
                      <Form.Item><Button type="primary" icon={<FolderOpenOutlined />} onClick={importLocalRepo}>导入</Button></Form.Item>
                    </Form>
                  </Card>
                ),
              },
              {
                key: 'manual',
                label: '手动注册',
                children: (
                  <Card title="手动注册 Git 仓库" bordered={false}>
                    <Form form={repoForm} layout="inline" initialValues={{ branch: 'main' }}>
                      <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="repo name" /></Form.Item>
                      <Form.Item name="url" rules={[{ required: true }]}><Input placeholder="git url" style={{ width: 360 }} /></Form.Item>
                      <Form.Item name="branch"><Input placeholder="branch" /></Form.Item>
                      <Form.Item><Button type="primary" onClick={registerRepo}>注册</Button></Form.Item>
                    </Form>
                  </Card>
                ),
              },
            ]}
          />
          <Card title="已注册仓库" bordered={false} className="admin-table-card">
            <Table
              {...responsiveTableProps}
              rowKey="name"
              dataSource={repos}
              columns={[
                { title: '名称', dataIndex: 'name', width: 220, ellipsis: true, render: renderEllipsisCell },
                { title: 'URL', dataIndex: 'url', ellipsis: true, render: renderEllipsisCell },
                { title: '本地路径', dataIndex: 'local_path', width: 180, ellipsis: true, render: renderEllipsisCell },
                { title: '分支', dataIndex: 'default_branch', width: 90 },
                { title: '来源', width: 90, render: (_: unknown, r: RepoRecord) => String(r.metadata?.source || '-') },
                { title: '状态', width: 160, render: (_: unknown, r: RepoRecord) => {
                  const state = r.sync_status?.state || 'pending'
                  const item = repoSyncStateLabels[state] || { color: 'default', text: state }
                  const errorMessage = r.sync_status?.error_message
                  return (
                    <Space direction="vertical" size={0} style={{ maxWidth: '100%' }}>
                      <Tag color={item.color}>{item.text}</Tag>
                      {state === 'pending' ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>仅注册，需点「同步/索引」</Typography.Text> : null}
                      {errorMessage ? (
                        <Tooltip title={errorMessage}>
                          <Typography.Text type="danger" style={{ fontSize: 12 }} className="table-cell-ellipsis">
                            {errorMessage}
                          </Typography.Text>
                        </Tooltip>
                      ) : null}
                    </Space>
                  )
                } },
                { title: '操作', width: 160, render: (_: unknown, r: RepoRecord) => <Space><Button onClick={() => syncRepo(r.name)}>同步/索引</Button><Button danger onClick={() => deleteRepo(r.name)}>删除</Button></Space> },
              ]}
            />
          </Card>
          <Modal
            title={editingRepoRemote ? `编辑远端源：${editingRepoRemote.name}` : '新增远端源'}
            open={repoRemoteModalOpen}
            onCancel={() => {
              setRepoRemoteModalOpen(false)
              setEditingRepoRemote(null)
              repoRemoteForm.resetFields()
            }}
            onOk={saveRepoRemote}
            okText="保存"
            cancelText="取消"
            width={760}
          >
            <Form form={repoRemoteForm} layout="vertical" initialValues={{ provider: 'github' }}>
              <div className="repo-remote-grid">
                <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                  <Input placeholder="github-main" disabled={Boolean(editingRepoRemote)} />
                </Form.Item>
                <Form.Item name="provider" label="类型" rules={[{ required: true }]}>
                  <Select
                    onChange={(provider) => {
                      const current = repoRemoteForm.getFieldValue('base_url')
                      const previousDefaults = Object.values(repoRemoteDefaultBaseUrl)
                      if (!current || previousDefaults.includes(current)) {
                        repoRemoteForm.setFieldValue('base_url', repoRemoteDefaultBaseUrl[String(provider)] || '')
                      }
                    }}
                    options={[
                      { label: 'GitHub', value: 'github' },
                      { label: 'Gitee', value: 'gitee' },
                      { label: '云效 / Codeup', value: 'yunxiao' },
                      { label: '自定义', value: 'custom' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="base_url" label="域名 / Base URL">
                  <Input placeholder="常见平台会自动填充，可改为私有域名" />
                </Form.Item>
                <Form.Item name="token" label="Token">
                  <Input.Password placeholder="留空则保留已有 Token" />
                </Form.Item>
                <Form.Item
                  name="owner"
                  label={
                    repoRemoteProvider === 'yunxiao'
                      ? 'organizationId（中心版必填）'
                      : '默认组织 / Group'
                  }
                  extra={
                    repoRemoteProvider === 'yunxiao'
                      ? '云效中心版 API 列表用；Region 版可留空'
                      : undefined
                  }
                >
                  <Input
                    placeholder={
                      repoRemoteProvider === 'yunxiao'
                        ? '例如 60de7a6852743a5162b5f957'
                        : 'GitHub/Gitee 可空'
                    }
                  />
                </Form.Item>
                {repoRemoteProvider === 'yunxiao' ? (
                  <Form.Item
                    name="git_username"
                    label="HTTPS 克隆账号"
                    extra="Codeup → 个人设置 → HTTPS 密码 → 克隆账号（不是 organizationId）"
                    rules={[{ required: true, message: '请填写 Codeup HTTPS 克隆账号' }]}
                  >
                    <Input placeholder="克隆账号" />
                  </Form.Item>
                ) : (
                  <Form.Item name="git_username" hidden>
                    <Input />
                  </Form.Item>
                )}
                <Form.Item name="api_path" label="自定义 API path">
                  <Input placeholder="云效/私有平台可填" />
                </Form.Item>
              </div>
            </Form>
          </Modal>
        </Space>
      )
    }
    if (active === 'catalog') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card title="新增/编辑服务" bordered={false}>
            <Form form={catalogForm} layout="inline">
              <Form.Item name="service_name" rules={[{ required: true }]}><Input placeholder="service_name" /></Form.Item>
              <Form.Item name="display_name"><Input placeholder="显示名称" /></Form.Item>
              <Form.Item name="owner_team"><Input placeholder="团队" /></Form.Item>
              <Form.Item name="language"><Input placeholder="语言" /></Form.Item>
              <Form.Item name="repositories"><Input placeholder='repositories JSON, 如 []' style={{ width: 260 }} /></Form.Item>
              <Form.Item><Button type="primary" onClick={saveCatalog}>保存服务</Button></Form.Item>
            </Form>
          </Card>
          <Card bordered={false}><Table rowKey="service_name" dataSource={catalogItems} columns={[{ title: '服务', dataIndex: 'service_name' }, { title: '名称', dataIndex: 'display_name' }, { title: '团队', dataIndex: 'owner_team' }, { title: '语言', dataIndex: 'language' }, { title: '操作', render: (_, r) => <Button danger onClick={() => deleteCatalog(r)}>删除</Button> }]} /></Card>
        </Space>
      )
    }
    if (active === 'mcpServers') {
      const enabledCount = mcpServers.filter((item) => item.enabled !== false).length
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space size={16}>
              <Typography.Text type="secondary">
                已启用 {enabledCount} / 共 {mcpServers.length} 个 Server
              </Typography.Text>
              <Tooltip title={renderAllMcpToolsTooltip(mcpServers)} placement="bottom">
                <Badge
                  count={mcpToolsTotal}
                  overflowCount={999}
                  color={mcpToolsTotal > 0 ? '#52c41a' : '#d9d9d9'}
                  showZero
                >
                  <Tag color={mcpToolsTotal > 0 ? 'success' : 'default'} style={{ cursor: 'help' }}>
                    可用工具 {mcpToolsTotal}
                  </Tag>
                </Badge>
              </Tooltip>
            </Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openMcpServerModal()}>
              添加 MCP Server
            </Button>
          </div>
          <Card bordered={false}>
            <Table
              rowKey="server_id"
              dataSource={mcpServers}
              expandable={{
                expandedRowRender: (record: McpServerRecord) => (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Typography.Text type="secondary">
                      命令：{record.command} {Array.isArray(record.args) ? record.args.join(' ') : ''}
                    </Typography.Text>
                    {record.last_sync_at ? (
                      <Typography.Text type="secondary">最近同步：{record.last_sync_at}</Typography.Text>
                    ) : null}
                    {record.last_error ? (
                      <Typography.Text type="danger">最近错误：{record.last_error}</Typography.Text>
                    ) : null}
                    <Table
                      size="small"
                      rowKey="name"
                      dataSource={(record.tools || []) as ApiRecord[]}
                      pagination={false}
                      columns={[
                        { title: '工具名', dataIndex: 'name' },
                        { title: '描述', dataIndex: 'description', ellipsis: true },
                        {
                          title: '注册名',
                          render: (_: unknown, tool: ApiRecord) => `ext.${record.server_id}.${tool.name}`,
                        },
                      ]}
                    />
                  </Space>
                ),
              }}
              columns={[
                { title: '名称', dataIndex: 'name' },
                { title: '传输', dataIndex: 'transport', width: 90 },
                { title: '命令', dataIndex: 'command', ellipsis: true, render: renderEllipsisCell },
                {
                  title: '状态',
                  width: 110,
                  render: (_: unknown, record: McpServerRecord) => {
                    const meta = mcpDiscoveryStatusMeta(record)
                    const tag = (
                      <Tag color={meta.color}>
                        {record.discovery_status === 'discovering' ? (
                          <Space size={4}>
                            <Spin size="small" />
                            {meta.text}
                          </Space>
                        ) : (
                          meta.text
                        )}
                      </Tag>
                    )
                    if (record.discovery_status === 'failed' && record.last_error) {
                      return (
                        <Tooltip title={record.last_error} placement="topLeft">
                          {tag}
                        </Tooltip>
                      )
                    }
                    if (record.discovery_status === 'discovering') {
                      return (
                        <Tooltip title="正在连接 MCP Server，首次 npx 可能需等待下载" placement="topLeft">
                          {tag}
                        </Tooltip>
                      )
                    }
                    return tag
                  },
                },
                {
                  title: '可用工具',
                  width: 110,
                  render: (_: unknown, record: McpServerRecord) => {
                    const count = Number(record.tools_count ?? (record.tools || []).length)
                    return (
                      <Tag color={count > 0 ? 'success' : record.last_error ? 'error' : 'default'}>
                        {count} 个
                      </Tag>
                    )
                  },
                },
                {
                  title: '工具列表',
                  ellipsis: true,
                  render: (_: unknown, record: McpServerRecord) => {
                    const names = getMcpServerToolNames(record)
                    if (!names.length) {
                      return <Typography.Text type="secondary">暂无，点击「同步工具」</Typography.Text>
                    }
                    const visible = names.slice(0, 6)
                    const overflow = names.length - visible.length
                    const content = (
                      <Space size={[4, 4]} wrap>
                        {visible.map((name) => (
                          <Tag key={name}>{name}</Tag>
                        ))}
                        {overflow > 0 ? <Tag style={{ cursor: 'help' }}>+{overflow}</Tag> : null}
                      </Space>
                    )
                    return (
                      <Tooltip title={renderMcpServerToolsTooltip(record)} placement="topLeft">
                        <span style={{ cursor: 'help' }}>{content}</span>
                      </Tooltip>
                    )
                  },
                },
                {
                  title: '启用',
                  width: 90,
                  render: (_: unknown, record: McpServerRecord) => (
                    <Switch
                      checked={record.enabled !== false}
                      onChange={(checked) => toggleMcpServer(record, checked)}
                    />
                  ),
                },
                {
                  title: '操作',
                  width: 280,
                  render: (_: unknown, record: McpServerRecord) => (
                    <Space>
                      <Button onClick={() => testMcpServer(record.server_id)}>测试</Button>
                      <Button onClick={() => syncMcpServerTools(record.server_id)}>同步工具</Button>
                      <Button icon={<EditOutlined />} onClick={() => openMcpServerModal(record)}>编辑</Button>
                      <Button danger onClick={() => deleteMcpServer(record.server_id)}>删除</Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
          <Modal
            title={editingMcpServer ? `编辑 MCP Server：${editingMcpServer.name}` : '添加 MCP Server'}
            open={mcpServerModalOpen}
            destroyOnHidden
            onCancel={() => {
              setMcpServerModalOpen(false)
              setEditingMcpServer(null)
              setMcpServerJsonText('')
            }}
            onOk={() => saveMcpServer()}
            okText="保存并发现工具"
            cancelText="取消"
            width={800}
            confirmLoading={mcpServerSaving}
            okButtonProps={{ disabled: mcpServerSaving }}
          >
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Text type="secondary">
                支持 Cursor 单条、mcpServers 块或 RootSeeker 格式。使用 npx 时建议 args 包含 -y（会自动补全），避免首次安装卡住。
              </Typography.Text>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button
                  type="link"
                  onClick={() => setMcpServerJsonText(JSON.stringify(MCP_SERVER_JSON_TEMPLATE, null, 2))}
                >
                  填入 PlantUML 示例
                </Button>
              </div>
              <Input.TextArea
                value={mcpServerJsonText}
                onChange={(e) => setMcpServerJsonText(e.target.value)}
                rows={16}
                style={{ fontFamily: 'Consolas, Monaco, monospace' }}
                placeholder='{"plantuml":{"command":"npx","args":["plantuml-mcp-server"],"env":{...}}}'
              />
            </Space>
          </Modal>
        </Space>
      )
    }
    if (active === 'notificationChannels') {
      const enabledCount = notificationChannels.filter((item) => item.enabled !== false).length
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography.Text type="secondary">
              已启用 {enabledCount} / 共 {notificationChannels.length}
            </Typography.Text>
            <Space>
              <span>全局广播</span>
              <Switch checked={broadcastEnabled} onChange={updateBroadcastEnabled} />
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openChannelModal()}>添加渠道</Button>
            </Space>
          </div>
          <Card bordered={false}>
            <Table
              rowKey="channel_id"
              dataSource={notificationChannels}
              columns={[
                { title: '名称', dataIndex: 'name' },
                {
                  title: '渠道',
                  dataIndex: 'channel_type',
                  render: (value: string) => <Tag>{value}</Tag>,
                },
                { title: 'URL', dataIndex: 'endpoint_url', ellipsis: true, render: renderEllipsisCell },
                {
                  title: '启用',
                  render: (_: unknown, record: NotificationChannelRecord) => (
                    <Switch
                      checked={record.enabled !== false}
                      onChange={(checked) => toggleNotificationChannel(record, checked)}
                    />
                  ),
                },
                {
                  title: '操作',
                  render: (_: unknown, record: NotificationChannelRecord) => (
                    <Space>
                      <Button onClick={() => testNotificationChannel(record.channel_id)}>测试</Button>
                      <Button icon={<EditOutlined />} onClick={() => openChannelModal(record)}>编辑</Button>
                      <Button danger onClick={() => deleteNotificationChannel(record.channel_id)}>删除</Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
          <Modal
            title={editingChannel ? `编辑通知渠道：${editingChannel.name}` : '添加通知渠道'}
            open={channelModalOpen}
            onCancel={() => {
              setChannelModalOpen(false)
              setEditingChannel(null)
              channelForm.resetFields()
            }}
            onOk={saveNotificationChannel}
            okText="保存"
            cancelText="取消"
            width={720}
          >
            <Form form={channelForm} layout="vertical">
              <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                <Input placeholder="运维飞书群" />
              </Form.Item>
              <Form.Item name="channel_type" label="渠道类型" rules={[{ required: true }]}>
                <Select
                  options={['webhook', 'feishu', 'dingtalk', 'wechat_work', 'slack', 'discord'].map((value) => ({
                    value,
                    label: value,
                  }))}
                />
              </Form.Item>
              <Form.Item name="endpoint_url" label="Webhook URL" rules={[{ required: true }]}>
                <Input placeholder="https://..." />
              </Form.Item>
              <Form.Item
                name="secret"
                label="加签密钥（可选）"
                extra="仅当机器人/Webhook 启用了「加签」安全设置时需要填写，例如钉钉自定义机器人的 SEC 密钥。普通 Webhook、飞书、Slack 等通常留空即可。"
              >
                <Input.Password placeholder="留空则保留已有密钥；未启用加签请留空" />
              </Form.Item>
              <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
                <Switch />
              </Form.Item>
            </Form>
          </Modal>
        </Space>
      )
    }
    if (active === 'schedules') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openCronModal()}>新增任务</Button>
          </div>
          <Card bordered={false}>
            <Table
              rowKey="job_id"
              dataSource={cronJobs}
              columns={[
                {
                  title: '名称',
                  render: (_, r) => (
                    <Space>
                      <span>{r.name}</span>
                      {r.builtin ? <Tag color="blue">内置</Tag> : null}
                    </Space>
                  ),
                },
                { title: 'Handler', dataIndex: 'handler' },
                { title: '调度', dataIndex: 'schedule' },
                { title: '时区', dataIndex: 'timezone' },
                {
                  title: '备注',
                  dataIndex: 'notes',
                  ellipsis: true,
                  render: (v: string | undefined) => v || <Typography.Text type="secondary">-</Typography.Text>,
                },
                {
                  title: '状态',
                  render: (_, r) => {
                    const raw =
                      r.enabled === false
                        ? 'disabled'
                        : r.state?.status === 'disabled'
                          ? 'idle'
                          : r.state?.status || 'idle'
                    const labels: Record<string, string> = {
                      idle: '空闲',
                      disabled: '已停用',
                      running: '运行中',
                      succeeded: '上次成功',
                      failed: '上次失败',
                    }
                    return labels[raw] || raw
                  },
                },
                {
                  title: '上次运行',
                  render: (_, r) => r.state?.last_finished_at || r.state?.last_started_at || '-',
                },
                {
                  title: '启用',
                  render: (_, r) => (
                    <Switch checked={r.enabled !== false} onChange={(checked) => toggleCronJob(r, checked)} />
                  ),
                },
                {
                  title: '操作',
                  render: (_, r) => (
                    <Space wrap>
                      <Button onClick={() => openCronModal(r)}>编辑</Button>
                      <Button onClick={() => runCronJob(r.job_id)}>立即执行</Button>
                      <Button onClick={() => openCronRuns(r.job_id)}>运行记录</Button>
                      {!r.builtin && r.deletable !== false ? (
                        <Button danger onClick={() => deleteCronJob(r.job_id)}>删除</Button>
                      ) : null}
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
          <Modal
            title={editingCronJob ? '编辑定时任务' : '新增定时任务'}
            open={cronModalOpen}
            onCancel={() => setCronModalOpen(false)}
            onOk={saveCronJob}
            destroyOnClose
          >
            <Form form={cronForm} layout="vertical">
              <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="handler" label="Handler" rules={[{ required: true }]}>
                <Select
                  disabled={Boolean(editingCronJob?.builtin)}
                  options={(cronHandlers.length ? cronHandlers : ['repo.sync_changed', 'repo.sync_all', 'replay.default_flow']).map((h) => ({
                    value: h,
                    label: h,
                  }))}
                />
              </Form.Item>
              <Form.Item
                name="schedule"
                label="调度"
                rules={[{ required: true }]}
                extra="支持 @hourly / @daily 或标准 5 段 cron，例如 0 * * * *"
              >
                <Input placeholder="@hourly" />
              </Form.Item>
              <Form.Item name="timezone" label="时区" initialValue="UTC">
                <Input placeholder="UTC" />
              </Form.Item>
              <Form.Item name="notes" label="备注">
                <Input.TextArea rows={3} placeholder="任务说明" />
              </Form.Item>
              <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
                <Switch />
              </Form.Item>
            </Form>
          </Modal>
          <Modal
            title="运行记录"
            open={cronRunsOpen}
            onCancel={() => setCronRunsOpen(false)}
            footer={[
              <Button key="refresh" onClick={() => cronRunsJobId && openCronRuns(cronRunsJobId)}>刷新</Button>,
              <Button key="close" type="primary" onClick={() => setCronRunsOpen(false)}>关闭</Button>,
            ]}
            width={720}
          >
            <Table
              rowKey={(r) => `${r.job_id}-${r.started_at}-${r.finished_at}`}
              dataSource={cronRuns}
              pagination={false}
              columns={[
                { title: '状态', dataIndex: 'status', width: 100 },
                { title: '开始', dataIndex: 'started_at' },
                { title: '结束', dataIndex: 'finished_at' },
                { title: '消息', dataIndex: 'message', ellipsis: true },
              ]}
            />
          </Modal>
        </Space>
      )
    }
    if (active === 'advanced') {
      const runtimeRows = [
        ['ZOEKT_ENDPOINT', 'Zoekt Endpoint', 'http://127.0.0.1:6070'],
        ['QDRANT_ENDPOINT', 'Qdrant Endpoint', 'http://127.0.0.1:6333'],
        ['ROOTSEEKER_REPO_BASE_PATH', 'Repo Base Path', 'data/admin-repos'],
        ['ROOTSEEKER_ZOEKT_INDEX_DIR', 'Zoekt Index Dir', 'data/zoekt/index'],
        ['ROOTSEEKER_EMBEDDING_PROVIDER', 'Embedding Provider', 'hash / openai_compatible / http'],
        ['ROOTSEEKER_EMBEDDING_DIMENSION', 'Embedding Dimension', '384 / 1536'],
        ['ROOTSEEKER_DEFAULT_AI_PROVIDER', 'Default AI Provider', 'deepseek'],
        ['ROOTSEEKER_DEFAULT_AI_MODEL', 'Default AI Model', 'deepseek-v4-pro'],
      ].map(([key, label, placeholder]) => ({
        key,
        label,
        placeholder,
        value: settingsData[key],
      }))
      return (
        <Card bordered={false}>
          <Tabs
            defaultActiveKey="runtime"
            items={[
              {
                key: 'runtime',
                label: '运行配置',
                children: (
                  <Table rowKey="key" dataSource={runtimeRows} columns={[
                    { title: '配置项', dataIndex: 'label' },
                    { title: '变量名', dataIndex: 'key' },
                    { title: '当前值', render: (_, r) => String(r.value ?? '') || <Typography.Text type="secondary">未设置</Typography.Text> },
                    { title: '说明/示例', dataIndex: 'placeholder' },
                    { title: '操作', render: (_, r) => <Button onClick={() => openRuntimeModal(r.key, r.value)}>编辑</Button> },
                  ]} pagination={false} />
                ),
              },
              {
                key: 'env',
                label: '环境变量',
                children: (
                  <Space direction="vertical" size={16} style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography.Text type="secondary">作用域为 runtime / mcp 的变量会注入 MCP 子进程环境；skill 仅给 Skill 使用。MCP Server JSON 里的 env 优先级更高。更新后已连接的 MCP 会话会重启以加载新变量。</Typography.Text>
                      <Button type="primary" onClick={() => openEnvModal()}>添加变量</Button>
                    </div>
                    <Table rowKey="key" dataSource={envVars} columns={[
                      { title: '变量名', dataIndex: 'key' },
                      { title: '值', render: (_, r) => r.secret ? r.masked_value : r.value },
                      { title: '作用域', dataIndex: 'scope' },
                      { title: '类型', render: (_, r) => r.secret ? <Tag color="red">secret</Tag> : <Tag>plain</Tag> },
                      { title: '操作', render: (_, r) => <Space><Button onClick={() => openEnvModal(r)}>编辑</Button><Button danger onClick={() => deleteEnvVar(r.key)}>删除</Button></Space> },
                    ]} pagination={false} />
                  </Space>
                ),
              },
              {
                key: 'preview',
                label: 'settings 预览',
                children: <pre>{JSON.stringify(settingsData, null, 2)}</pre>,
              },
            ]}
          />
        </Card>
      )
    }
    if (active === 'semantic') {
      return <Space direction="vertical" size={16} style={{ width: '100%' }}><Card title="语义搜索" bordered={false}><Form form={semanticForm} layout="inline"><Form.Item name="query" rules={[{ required: true }]}><Input placeholder="查询内容" style={{ width: 360 }} /></Form.Item><Form.Item name="repo_name"><Input placeholder="repo，可空" /></Form.Item><Form.Item name="limit" initialValue={10}><Input type="number" style={{ width: 100 }} /></Form.Item><Form.Item><Button type="primary" onClick={runSemanticSearch}>搜索</Button></Form.Item></Form></Card><Card title="搜索结果" bordered={false}><pre>{JSON.stringify(semanticResult, null, 2)}</pre></Card></Space>
    }
    if (active === 'errorChat') {
      return (
        <div className={`error-chat-page ${historyCollapsed ? 'history-collapsed' : ''}`}>
          <Card bordered={false} className="error-history-panel">
            <button className="history-edge-toggle" onClick={() => setHistoryCollapsed(true)}>‹</button>
            <div className="error-history-head">
              <Typography.Title level={5}>历史记录</Typography.Title>
              <Button danger size="small" onClick={clearErrorChat} disabled={!errorChatItems.length}>清空</Button>
            </div>
            {errorChatItems.length ? (
              <div className="error-history-list">
                {errorChatItems.map((item) => (
                  <button className="history-row" key={item.id} onClick={() => {
                    setErrorChatInput(item.content)
                    errorCaseForm.setFieldsValue(item.request || {})
                    setErrorChatResult(item)
                  }}>
                    <div className="history-row-title">{item.content.slice(0, 48) || item.case?.title || '错误信息'}</div>
                    <div className="history-row-sub">
                      {item.case?.status || 'submitted'} · evidence {item.evidence_count ?? 0}
                    </div>
                    <div className="history-time">{item.created_at}</div>
                  </button>
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史记录" />
            )}
          </Card>
          <div className="history-drawer-rail">
            <button className="history-edge-toggle collapsed-toggle" onClick={() => setHistoryCollapsed(false)}>›</button>
          </div>
          <div className="error-chat-main">
            <div className="error-hero">
              <Typography.Title level={2}>错误排查工作台</Typography.Title>
              <Typography.Text type="secondary">提交错误信息后会创建 Case，执行排查 Flow，并返回证据、步骤和报告。</Typography.Text>
            </div>
            <Card bordered={false} className="error-input-card">
              <Form form={errorCaseForm} layout="inline" initialValues={{ environment: 'prod', severity: 'error', trace_id: '' }}>
                <Form.Item name="service_name"><Input placeholder="service_name（可选，留空自动识别）" allowClear style={{ minWidth: 240 }} /></Form.Item>
                <Form.Item name="environment"><Input placeholder="environment" /></Form.Item>
                <Form.Item name="severity"><Select style={{ width: 120 }} options={['info', 'warning', 'error', 'critical'].map(v => ({ value: v, label: v }))} /></Form.Item>
                <Form.Item name="trace_id"><Input placeholder="trace_id（可选）" allowClear /></Form.Item>
              </Form>
              <Input.TextArea
                value={errorChatInput}
                disabled={errorChatSubmitting}
                onChange={(event) => setErrorChatInput(event.target.value)}
                placeholder="粘贴错误堆栈、日志片段、异常现象或复现步骤..."
                autoSize={{ minRows: 5, maxRows: 12 }}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault()
                    submitErrorChat()
                  }
                }}
              />
              <div className="error-input-actions">
                <Button type="primary" shape="circle" loading={errorChatSubmitting} icon={<MessageOutlined />} onClick={submitErrorChat} />
              </div>
            </Card>
            {errorChatResult ? (
              <Card bordered={false} className="error-result-card" title="排查结果">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div><b>Case ID：</b>{errorChatResult.case?.case_id || '-'}</div>
                  <div><b>Flow Run ID：</b>{errorChatResult.flow_run_id || '-'}</div>
                  <div><b>状态：</b>{errorChatResult.case?.status || '-'}</div>
                  <div><b>服务：</b>{errorChatResult.case?.service_name || '-'}</div>
                  <div><b>证据数：</b>{errorChatResult.evidence_count ?? 0}</div>
                  <div><b>证据摘要：</b>{errorChatResult.evidence_summary || '-'}</div>
                  <div><b>流程耗时：</b>{errorChatResult.flow_elapsed_ms ?? '-'}ms</div>
                  <div><b>根因：</b>{errorChatResult.report?.root_cause?.title || '暂无明确根因'}</div>
                  <div>
                    <b>AI 分析：</b>
                    {errorChatResult.ai_analysis?.ok
                      ? `${errorChatResult.ai_analysis.provider}/${errorChatResult.ai_analysis.model} · ${errorChatResult.ai_analysis.elapsed_ms}ms`
                      : errorChatResult.ai_analysis?.pending
                        ? '分析中，结果会自动刷新'
                      : `未完成（${errorChatResult.ai_analysis?.reason || errorChatResult.ai_analysis?.error || 'unknown'}）`}
                  </div>
                  {errorChatResult.ai_analysis?.content ? (
                    <div className="ai-analysis-content">{errorChatResult.ai_analysis.content}</div>
                  ) : null}
                  <details>
                    <summary>查看排查步骤</summary>
                    <Table
                      size="small"
                      rowKey="step_id"
                      dataSource={errorChatResult.case?.steps || []}
                      columns={[
                        { title: 'Step', dataIndex: 'name' },
                        { title: 'Tool', dataIndex: 'tool_name' },
                        { title: 'Status', dataIndex: 'status' },
                      ]}
                      pagination={false}
                    />
                  </details>
                  <details>
                    <summary>查看证据明细</summary>
                    <Table
                      size="small"
                      rowKey="item_id"
                      dataSource={errorChatResult.evidence_items || []}
                      columns={[
                        { title: 'ID', dataIndex: 'item_id' },
                        { title: '类型', dataIndex: 'type' },
                        { title: '来源', dataIndex: 'source' },
                        { title: '采集时间', dataIndex: 'collected_at' },
                        {
                          title: '内容',
                          render: (_: unknown, record: ErrorChatEvidence) => (
                            <pre>{JSON.stringify(record.content || {}, null, 2)}</pre>
                          ),
                        },
                      ]}
                      pagination={false}
                    />
                  </details>
                  <details>
                    <summary>查看工具调用</summary>
                    <pre>{JSON.stringify(errorChatResult.tool_results || [], null, 2)}</pre>
                  </details>
                  <details>
                    <summary>查看完整报告 JSON</summary>
                    <pre>{JSON.stringify(errorChatResult.report || {}, null, 2)}</pre>
                  </details>
                </Space>
              </Card>
            ) : null}
          </div>
        </div>
      )
    }
    return <PlaceholderPage title="暂未实现" description="该页面会继续完善。" />
  }

  const enabledModelsFor = (provider: AiProvider) => {
    const allModels = provider.metadata?.models || (provider.model ? [provider.model] : [])
    const disabled = new Set(provider.metadata?.disabled_models || [])
    return allModels.filter((model) => model && !disabled.has(model))
  }

  const modelPoolProviders = providers
    .map((provider) => ({ provider, models: enabledModelsFor(provider) }))
    .filter(({ provider, models }) => Boolean(provider.api_key) && models.length > 0)

  return (
    <ConfigProvider
      theme={{
        token: { colorPrimary: '#e85d75', borderRadius: 12 },
        components: { Button: { controlHeight: 36 } },
      }}
    >
      <AntApp>
        {contextHolder}
        <Layout className="admin-layout">
          <Layout.Sider width={210} theme="light" className="admin-sider">
            <div className="brand"><span className="brand-icon">R</span><span>RootSeeker</span></div>
            <Menu selectedKeys={[active]} mode="inline" items={menuItems} onClick={(info) => navigateTo(info.key)} />
          </Layout.Sider>
          <Layout.Content className="admin-content">
            {active !== 'errorChat' && (
              <div className="topbar">
                <div>
                  <Typography.Title level={2} style={{ marginBottom: 6 }}>{meta.title}</Typography.Title>
                  <Typography.Text type="secondary">{meta.desc}</Typography.Text>
                </div>
                <Badge status="success" text="正常" />
              </div>
            )}

            {renderContent()}
          </Layout.Content>
        </Layout>

        <Modal
          open={providerModalOpen}
          title={editingProvider ? `配置 ${providerDisplay(editingProvider)}` : '添加自定义提供商'}
          onCancel={() => setProviderModalOpen(false)}
          onOk={saveProvider}
          okText={editingProvider ? '保存' : '创建'}
          cancelText="取消"
          width={760}
        >
          <Form form={form} layout="vertical" className="provider-form">
            <Form.Item label="提供商 ID" name="name" rules={[{ required: true, message: '请输入提供商 ID' }]} extra="仅支持小写字母、数字、连字符、下划线，创建后不可更改。">
              <Input placeholder="如 openai, google, anthropic" disabled={Boolean(editingProvider)} />
            </Form.Item>
            <Form.Item label="显示名称" name="display_name" rules={[{ required: true, message: '请输入显示名称' }]}>
              <Input placeholder="如 OpenAI, Google Gemini" />
            </Form.Item>
            <Form.Item label="接入地址" name="base_url" extra="OpenAI 兼容端点，如 http://localhost:11434/v1">
              <Input placeholder="如 https://api.openai.com/v1" />
            </Form.Item>
            <Form.Item label="API 密钥" name="api_key">
              <Input.Password placeholder="输入 API 密钥（可选，可稍后设置）" />
            </Form.Item>
            <Form.Item
              label="思考模式"
              name="reasoning_enabled"
              valuePropName="checked"
              extra="启用深度思考（思维链）能力。关闭后，该服务商下所有模型将禁用思考模式。"
            >
              <Switch />
            </Form.Item>
            <Form.Item label="协议类型" name="provider_type" initialValue="openai_compatible" extra="选择与目标 API 兼容的协议类型">
              <Select
                options={[
                  { value: 'openai_compatible', label: '默认（OpenAI 兼容）' },
                  { value: 'anthropic_messages', label: 'Anthropic Messages' },
                ]}
              />
            </Form.Item>
            <Divider>管理模型</Divider>
            {models.length ? models.map((model, index) => (
              <div className="model-setting-row" key={`${model}-${index}`}>
                <Switch checked={!disabledModels.includes(model)} onChange={(checked) => setDisabledModels(checked ? disabledModels.filter((item) => item !== model) : [...disabledModels, model])} />
                <Input value={model} onChange={(event) => setModels(models.map((item, idx) => idx === index ? event.target.value : item))} />
                <Tag color="green">内置</Tag>
              </div>
            )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无模型" />}
            <Button block icon={<PlusOutlined />} onClick={() => setModels([...models, ''])}>添加模型</Button>
          </Form>
        </Modal>

        <Modal
          open={runtimeModalOpen}
          title="编辑运行时配置"
          okText="保存"
          cancelText="取消"
          onCancel={() => {
            setRuntimeModalOpen(false)
            setEditingRuntimeKey(null)
          }}
          onOk={saveRuntimeSettings}
        >
          <Form form={runtimeForm} layout="vertical">
            {editingRuntimeKey ? (
              <Form.Item label={editingRuntimeKey} name={editingRuntimeKey}>
                <Input />
              </Form.Item>
            ) : null}
          </Form>
        </Modal>

        <Modal
          open={envModalOpen}
          title="编辑环境变量"
          okText="保存"
          cancelText="取消"
          onCancel={() => setEnvModalOpen(false)}
          onOk={saveEnvVar}
        >
          <Form form={envForm} layout="vertical">
            <Form.Item label="变量名" name="key" rules={[{ required: true }]}>
              <Input placeholder="OPENAI_API_KEY" />
            </Form.Item>
            <Form.Item label="变量值" name="value">
              <Input.Password />
            </Form.Item>
            <Form.Item label="作用域" name="scope" initialValue="runtime">
              <Select options={[{ value: 'runtime', label: 'runtime' }, { value: 'skill', label: 'skill' }, { value: 'mcp', label: 'mcp' }]} />
            </Form.Item>
            <Form.Item label="是否密钥" name="secret" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Form>
        </Modal>
      </AntApp>
    </ConfigProvider>
  )
}

export default App
