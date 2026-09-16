import { Button, Card, Form, Input, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { api } from './App.tsx'

type AuthStatus = {
  authenticated: boolean
  needs_bootstrap: boolean
}

const safeNext = (): string => {
  const next = new URLSearchParams(window.location.search).get('next') || ''
  if (next.startsWith('/') && !next.startsWith('//')) {
    return next
  }
  return ''
}

export default function LoginPage() {
  const [needsBootstrap, setNeedsBootstrap] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [form] = Form.useForm()

  useEffect(() => {
    void api<AuthStatus>('/api/auth/status')
      .then((status) => {
        if (status.authenticated) {
          window.location.replace(safeNext() || '/overview')
          return
        }
        setNeedsBootstrap(Boolean(status.needs_bootstrap))
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  const onFinish = async (values: { username: string; password: string; confirmPassword?: string }) => {
    setError('')
    setSubmitting(true)
    try {
      const url = needsBootstrap ? '/api/auth/bootstrap' : '/api/auth/login'
      await api(url, {
        method: 'POST',
        body: JSON.stringify({ username: values.username, password: values.password }),
      })
      window.location.replace(safeNext() || '/overview')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card" title={needsBootstrap ? '创建首个账号' : '登录'} loading={loading}>
        {error ? (
          <Typography.Paragraph type="danger" style={{ marginBottom: 16 }}>
            {error}
          </Typography.Paragraph>
        ) : null}
        <Form form={form} layout="vertical" onFinish={(values) => void onFinish(values)}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete={needsBootstrap ? 'new-password' : 'current-password'} />
          </Form.Item>
          {needsBootstrap ? (
            <Form.Item
              name="confirmPassword"
              label="确认密码"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('两次输入的密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          ) : null}
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={submitting}>
              {needsBootstrap ? '创建首个账号' : '登录'}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
