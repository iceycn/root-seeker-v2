import {
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
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
  Switch,
  Table,
  Tag,
  Tabs,
  Typography,
  message,
} from 'antd'
import type { MenuProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import './App.css'

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

const api = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) throw new Error(data?.detail || text || response.statusText)
  return data as T
}

const maskKey = (key?: string) => {
  if (!key) return '未设置'
  if (key.length <= 8) return `${key.slice(0, 2)}******`
  return `${key.slice(0, 3)}******${key.slice(-4)}`
}

const providerDisplay = (provider: AiProvider) =>
  provider.metadata?.display_name || provider.name

const pathToView: Record<string, string> = {
  '/': 'models',
  '/admin': 'models',
  '/models': 'models',
  '/advanced-settings': 'advanced',
  '/skills': 'skills',
  '/repos': 'repos',
  '/catalog': 'catalog',
  '/plugins': 'plugins',
  '/callbacks': 'callbacks',
  '/semantic-search': 'semantic',
  '/overview': 'overview',
}

const viewToPath: Record<string, string> = {
  models: '/models',
  advanced: '/advanced-settings',
  skills: '/skills',
  repos: '/repos',
  catalog: '/catalog',
  plugins: '/plugins',
  callbacks: '/callbacks',
  semantic: '/semantic-search',
  errorChat: '/error-chat',
  overview: '/overview',
}

function App() {
  const [active, setActive] = useState(() => pathToView[window.location.pathname] || 'models')
  const [providers, setProviders] = useState<AiProvider[]>([])
  const [defaultProvider, setDefaultProvider] = useState<string | null>(null)
  const [defaultModel, setDefaultModel] = useState<string | null>(null)
  const [statusData, setStatusData] = useState<any>(null)
  const [skills, setSkills] = useState<any[]>([])
  const [plugins, setPlugins] = useState<any[]>([])
  const [tools, setTools] = useState<any[]>([])
  const [repos, setRepos] = useState<any[]>([])
  const [catalogItems, setCatalogItems] = useState<any[]>([])
  const [callbacksData, setCallbacksData] = useState<any[]>([])
  const [settingsData, setSettingsData] = useState<Record<string, unknown>>({})
  const [envVars, setEnvVars] = useState<any[]>([])
  const [providerModalOpen, setProviderModalOpen] = useState(false)
  const [envModalOpen, setEnvModalOpen] = useState(false)
  const [runtimeModalOpen, setRuntimeModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<AiProvider | null>(null)
  const [editingRuntimeKey, setEditingRuntimeKey] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [disabledModels, setDisabledModels] = useState<string[]>([])
  const [form] = Form.useForm()
  const [repoForm] = Form.useForm()
  const [catalogForm] = Form.useForm()
  const [callbackForm] = Form.useForm()
  const [skillForm] = Form.useForm()
  const [semanticForm] = Form.useForm()
  const [errorCaseForm] = Form.useForm()
  const [envForm] = Form.useForm()
  const [runtimeForm] = Form.useForm()
  const [semanticResult, setSemanticResult] = useState<unknown>(null)
  const [errorChatItems, setErrorChatItems] = useState<any[]>([])
  const [errorChatInput, setErrorChatInput] = useState('')
  const [historyCollapsed, setHistoryCollapsed] = useState(false)
  const [errorChatSubmitting, setErrorChatSubmitting] = useState(false)
  const [errorChatResult, setErrorChatResult] = useState<any>(null)
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
    skills: { title: 'Skills 管理', desc: '查看内置技能，快速创建和删除自定义 Skill。' },
    plugins: { title: 'Plugins / Tools', desc: '查看已加载插件和 MCP 工具注册情况。' },
    repos: { title: 'Repo 管理', desc: '注册仓库、同步代码并触发 Zoekt/Qdrant 索引。' },
    catalog: { title: 'Service Catalog', desc: '配置 service_name 到仓库、日志源、负责人等信息的映射。' },
    models: { title: '大语言模型', desc: '系统会根据用户内容智能选择最合适的模型，您也可以切换默认模型。' },
    callbacks: { title: '消息回调', desc: '配置通知通道、回调地址，并测试回调是否可达。' },
    advanced: { title: '高级设置', desc: '管理 Skill/MCP 运行时环境变量与 RootSeeker 运行时配置。' },
  }

  const loadProviders = async () => {
    const data = await api<{ items: AiProvider[]; default_provider: string | null; default_model?: string | null }>('/api/ai-providers')
    setProviders(data.items)
    setDefaultProvider(data.default_provider)
    setDefaultModel(data.default_model || null)
  }

  useEffect(() => {
    loadProviders().catch((error) => apiMessage.error(String(error)))
    const onPopState = () => setActive(pathToView[window.location.pathname] || 'models')
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  useEffect(() => {
    if (active === 'overview') api<any>('/api/status').then(setStatusData).catch((e) => apiMessage.error(String(e)))
    if (active === 'skills') api<any>('/api/skills').then((d) => setSkills(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'plugins') {
      api<any>('/api/plugins').then((d) => setPlugins(d.items || [])).catch((e) => apiMessage.error(String(e)))
      api<any>('/api/tools').then((d) => setTools(d.items || [])).catch((e) => apiMessage.error(String(e)))
    }
    if (active === 'repos') api<any>('/api/repos').then((d) => setRepos(d.repos || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'catalog') api<any>('/api/catalog').then((d) => setCatalogItems(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'callbacks') api<any>('/api/callbacks').then((d) => setCallbacksData(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'errorChat') api<any>('/api/error-chat').then((d) => setErrorChatItems(d.items || [])).catch((e) => apiMessage.error(String(e)))
    if (active === 'advanced') {
      api<any>('/api/settings').then((d) => {
        setSettingsData(d.settings || {})
        runtimeForm.setFieldsValue(d.settings || {})
      }).catch((e) => apiMessage.error(String(e)))
      api<any>('/api/env-vars').then((d) => setEnvVars(d.items || [])).catch((e) => apiMessage.error(String(e)))
    }
  }, [active])

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
    const data = await api<{ repos: any[] }>('/api/repos')
    setRepos(data.repos || [])
  }

  const registerRepo = async () => {
    const values = await repoForm.validateFields()
    await api('/api/repos', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('仓库已注册')
    await refreshRepos()
  }

  const syncRepo = async (name: string) => {
    await api(`/api/repos/${encodeURIComponent(name)}/sync`, {
      method: 'POST',
      body: JSON.stringify({ trigger_index: true }),
    })
    apiMessage.success('仓库同步/索引已完成')
    await refreshRepos()
  }

  const deleteRepo = async (name: string) => {
    await api(`/api/repos/${encodeURIComponent(name)}`, { method: 'DELETE' })
    apiMessage.success('仓库已删除')
    await refreshRepos()
  }

  const refreshCatalog = async () => {
    const data = await api<{ items: any[] }>('/api/catalog')
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

  const deleteCatalog = async (record: any) => {
    await api(`/api/catalog/${record.tenant}/${record.environment}/${encodeURIComponent(record.service_name)}`, { method: 'DELETE' })
    apiMessage.success('服务已删除')
    await refreshCatalog()
  }

  const refreshCallbacks = async () => {
    const data = await api<{ items: any[] }>('/api/callbacks')
    setCallbacksData(data.items || [])
  }

  const saveCallback = async () => {
    const values = await callbackForm.validateFields()
    await api('/api/callbacks', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('回调已保存')
    await refreshCallbacks()
  }

  const testCallback = async (name: string) => {
    const data = await api<{ ok: boolean; status_code?: number; error?: string }>(`/api/callbacks/${encodeURIComponent(name)}/test`, { method: 'POST' })
    if (data.ok) apiMessage.success(`回调连接正常（HTTP ${data.status_code ?? 'OK'}）`)
    else apiMessage.error(`回调测试失败：${data.error || data.status_code || 'unknown'}`)
  }

  const deleteCallback = async (name: string) => {
    await api(`/api/callbacks/${encodeURIComponent(name)}`, { method: 'DELETE' })
    apiMessage.success('回调已删除')
    await refreshCallbacks()
  }

  const saveQuickSkill = async () => {
    const values = await skillForm.validateFields()
    await api('/api/skills/quick', { method: 'POST', body: JSON.stringify(values) })
    apiMessage.success('Skill 已保存')
    const data = await api<{ items: any[] }>('/api/skills')
    setSkills(data.items || [])
  }

  const runSemanticSearch = async () => {
    const values = await semanticForm.validateFields()
    const data = await api('/api/code/semantic-search', { method: 'POST', body: JSON.stringify(values) })
    setSemanticResult(data)
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
      const data = await api<{ item: any; items: any[] }>('/api/error-chat', {
        method: 'POST',
        body: JSON.stringify({ ...formValues, content }),
      })
      setErrorChatItems(data.items || [])
      setErrorChatResult(data.item)
      setErrorChatInput('')
      apiMessage.success('排查流程已完成')
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
    const data = await api<{ items: any[] }>('/api/env-vars')
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

  const openEnvModal = (record?: any) => {
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
    { key: 'repos', icon: <FolderOpenOutlined />, label: 'Repo 管理' },
    { key: 'catalog', icon: <HeartOutlined />, label: 'Service Catalog' },
    { key: 'settings', label: '设置', type: 'group' },
    { key: 'models', icon: <RobotOutlined />, label: '大模型' },
    { key: 'callbacks', icon: <MessageOutlined />, label: '消息回调' },
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
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card title="快速创建 Custom Skill" bordered={false}>
            <Form form={skillForm} layout="inline">
              <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="名称" /></Form.Item>
              <Form.Item name="slug" rules={[{ required: true }]}><Input placeholder="custom/example" /></Form.Item>
              <Form.Item name="tags"><Input placeholder="tags 逗号分隔" /></Form.Item>
              <Form.Item><Button type="primary" onClick={saveQuickSkill}>保存</Button></Form.Item>
            </Form>
          </Card>
          <Card bordered={false}><Table rowKey="slug" dataSource={skills} columns={[{ title: 'Slug', dataIndex: 'slug' }, { title: '名称', dataIndex: 'name' }, { title: '版本', dataIndex: 'version' }, { title: '来源', dataIndex: 'source_kind' }]} /></Card>
        </Space>
      )
    }
    if (active === 'plugins') {
      return <Space direction="vertical" style={{ width: '100%' }} size={16}><Card title="Plugins" bordered={false}><Table rowKey="plugin_id" dataSource={plugins} columns={[{ title: 'ID', dataIndex: 'plugin_id' }, { title: '名称', dataIndex: 'display_name' }, { title: '类型', dataIndex: 'kind' }]} /></Card><Card title="Tools" bordered={false}><Table rowKey="name" dataSource={tools} columns={[{ title: '名称', dataIndex: 'name' }, { title: 'Scope', dataIndex: 'scope' }, { title: 'Server', dataIndex: 'server_name' }]} /></Card></Space>
    }
    if (active === 'repos') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card title="注册仓库" bordered={false}>
            <Form form={repoForm} layout="inline">
              <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="repo name" /></Form.Item>
              <Form.Item name="url" rules={[{ required: true }]}><Input placeholder="git url or local path" style={{ width: 360 }} /></Form.Item>
              <Form.Item name="branch" initialValue="main"><Input placeholder="branch" /></Form.Item>
              <Form.Item><Button type="primary" onClick={registerRepo}>注册</Button></Form.Item>
            </Form>
          </Card>
          <Card bordered={false}><Table rowKey="name" dataSource={repos} columns={[{ title: '名称', dataIndex: 'name' }, { title: 'URL', dataIndex: 'url' }, { title: '分支', dataIndex: 'default_branch' }, { title: '状态', render: (_, r) => r.sync_status?.state }, { title: '操作', render: (_, r) => <Space><Button onClick={() => syncRepo(r.name)}>同步索引</Button><Button danger onClick={() => deleteRepo(r.name)}>删除</Button></Space> }]} /></Card>
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
    if (active === 'callbacks') {
      return (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card title="新增/编辑回调" bordered={false}>
            <Form form={callbackForm} layout="inline">
              <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="名称" /></Form.Item>
              <Form.Item name="channel" initialValue="webhook"><Select style={{ width: 150 }} options={['webhook','feishu','dingtalk','wechat_work','slack','discord'].map(v => ({ value: v, label: v }))} /></Form.Item>
              <Form.Item name="url" rules={[{ required: true }]}><Input placeholder="回调 URL" style={{ width: 360 }} /></Form.Item>
              <Form.Item name="team" initialValue="default"><Input placeholder="team" /></Form.Item>
              <Form.Item><Button type="primary" onClick={saveCallback}>保存</Button></Form.Item>
            </Form>
          </Card>
          <Card bordered={false}><Table rowKey="name" dataSource={callbacksData} columns={[{ title: '名称', dataIndex: 'name' }, { title: '通道', dataIndex: 'channel' }, { title: 'URL', dataIndex: 'url' }, { title: 'Team', dataIndex: 'team' }, { title: '操作', render: (_, r) => <Space><Button onClick={() => testCallback(r.name)}>测试</Button><Button danger onClick={() => deleteCallback(r.name)}>删除</Button></Space> }]} /></Card>
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
                      <Typography.Text type="secondary">这些变量会写入管理端配置，并作为 Skill / MCP 运行时配置来源。更新模块暂不包含。</Typography.Text>
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
                    setErrorChatResult(item)
                  }}>
                    <div className="history-row-title">{item.case?.title || item.content.slice(0, 32) || '错误信息'}</div>
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
              <Form form={errorCaseForm} layout="inline" initialValues={{ service_name: 'order-service', environment: 'prod', severity: 'error', trace_id: 'trace-admin-error-chat' }}>
                <Form.Item name="service_name" rules={[{ required: true }]}><Input placeholder="service_name" /></Form.Item>
                <Form.Item name="environment"><Input placeholder="environment" /></Form.Item>
                <Form.Item name="severity"><Select style={{ width: 120 }} options={['info', 'warning', 'error', 'critical'].map(v => ({ value: v, label: v }))} /></Form.Item>
                <Form.Item name="trace_id"><Input placeholder="trace_id" /></Form.Item>
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
                  <div><b>状态：</b>{errorChatResult.case?.status || '-'}</div>
                  <div><b>服务：</b>{errorChatResult.case?.service_name || '-'}</div>
                  <div><b>证据数：</b>{errorChatResult.evidence_count ?? 0}</div>
                  <div><b>流程耗时：</b>{errorChatResult.flow_elapsed_ms ?? '-'}ms</div>
                  <div><b>根因：</b>{errorChatResult.report?.root_cause?.title || '暂无明确根因'}</div>
                  <div>
                    <b>AI 分析：</b>
                    {errorChatResult.ai_analysis?.ok
                      ? `${errorChatResult.ai_analysis.provider}/${errorChatResult.ai_analysis.model} · ${errorChatResult.ai_analysis.elapsed_ms}ms`
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
