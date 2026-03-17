import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Typography, message, Spin } from 'antd';
import { LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { checkSetup, setupPassword, login } from '@/api';
import './LoginPage.css';

const { Title, Text } = Typography;

interface LoginPageProps {
  onLoginSuccess: (token: string) => void;
}

const LoginPage: React.FC<LoginPageProps> = ({ onLoginSuccess }) => {
  const [hasPassword, setHasPassword] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadSetupStatus();
  }, []);

  const loadSetupStatus = async () => {
    try {
      const { data } = await checkSetup();
      setHasPassword(data.has_password);
    } catch {
      message.error('无法连接服务器');
    }
  };

  const handleSubmit = async (values: { password: string; confirm?: string }) => {
    setLoading(true);
    try {
      if (hasPassword) {
        const { data } = await login(values.password);
        localStorage.setItem('token', data.access_token);
        message.success('登录成功');
        onLoginSuccess(data.access_token);
      } else {
        if (!values.confirm) {
          message.error('请确认密码');
          return;
        }
        const { data } = await setupPassword(values.password, values.confirm);
        localStorage.setItem('token', data.access_token);
        message.success('密码设置成功');
        onLoginSuccess(data.access_token);
      }
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败');
    } finally {
      setLoading(false);
    }
  };

  if (hasPassword === null) {
    return (
      <div className="login-loading">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="logo-container">
          <div className="logo-icon-wrapper">
            <SafetyCertificateOutlined style={{ fontSize: 40, color: '#fff' }} />
          </div>
          <Title level={3} style={{ marginBottom: 4, fontWeight: 600 }}>
            {hasPassword ? '欢迎回来' : '初始化设置'}
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            {hasPassword ? '输入主密码以解锁您的账号数据' : '设置主密码来保护您的数据安全'}
          </Text>
        </div>

        <Form form={form} onFinish={handleSubmit} layout="vertical" size="large">
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码长度至少 6 位' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="输入主密码"
            />
          </Form.Item>

          {!hasPassword && (
            <Form.Item
              name="confirm"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
                placeholder="再次确认密码"
              />
            </Form.Item>
          )}

          <Form.Item style={{ marginBottom: 12 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={loading}
              style={{
                height: 44,
                fontSize: 15,
                fontWeight: 500,
                borderRadius: 10,
              }}
            >
              {hasPassword ? '解锁' : '开始使用'}
            </Button>
          </Form.Item>

          <div className="login-footer">
            <Text type="secondary" style={{ fontSize: 12 }}>
              <LockOutlined style={{ marginRight: 4 }} />
              数据使用 AES-256 加密，仅存储在本地
            </Text>
          </div>
        </Form>
      </div>
    </div>
  );
};

export default LoginPage;
