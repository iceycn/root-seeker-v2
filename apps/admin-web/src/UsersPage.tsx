import { PlusOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Modal, Popconfirm, Table, message } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { api } from './App.tsx'

type AdminUser = {
  id: string
  username: string
  created_at: string
}

export default function UsersPage() {
  const [items, setItems] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api<{ items: AdminUser[]; total: number }>('/api/users')
      setItems(data.items || [])
    } catch (error) {
      message.error(String(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const createUser = async () => {
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      await api('/api/users', {
        method: 'POST',
        body: JSON.stringify({ username: values.username, password: values.password }),
      })
      message.success('用户已创建')
      form.resetFields()
      setModalOpen(false)
      await reload()
    } catch (error) {
      message.error(String(error))
    } finally {
      setSubmitting(false)
    }
  }

  const deleteUser = async (id: string) => {
    try {
      await api(`/api/users/${encodeURIComponent(id)}`, { method: 'DELETE' })
      message.success('用户已删除')
      await reload()
    } catch (error) {
      message.error(String(error))
    }
  }

  return (
    <Card
      bordered={false}
      className="admin-table-card"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建用户
        </Button>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        pagination={false}
        columns={[
          { title: '用户名', dataIndex: 'username' },
          { title: '创建时间', dataIndex: 'created_at' },
          {
            title: '删除',
            render: (_: unknown, record: AdminUser) => (
              <Popconfirm title="确认删除该用户？" onConfirm={() => void deleteUser(record.id)}>
                <Button type="link" danger>
                  删除
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
      <Modal
        title="新建用户"
        open={modalOpen}
        okText="创建"
        cancelText="取消"
        confirmLoading={submitting}
        onCancel={() => {
          setModalOpen(false)
          form.resetFields()
        }}
        onOk={() => void createUser()}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
