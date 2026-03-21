import React, { useEffect, useState } from 'react';
import {
  Card,
  Switch,
  Select,
  Typography,
  Space,
  App,
  Spin,
  Divider,
  Tag,
  Alert,
} from 'antd';
import {
  BugOutlined,
  CameraOutlined,
  FileTextOutlined,
  EyeInvisibleOutlined,
  PhoneOutlined,
} from '@ant-design/icons';
import { getSettings, updateSettings, getSmsProviders, type Settings } from '@/api';
import type { SmsProviderConfig } from '@/api/sms';

const { Text, Paragraph } = Typography;

const SettingsPage: React.FC = () => {
  const { message } = App.useApp();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providers, setProviders] = useState<SmsProviderConfig[]>([]);

  const fetchSettings = async () => {
    try {
      const [settingsRes, providersRes] = await Promise.all([getSettings(), getSmsProviders()]);
      setSettings(settingsRes.data);
      setProviders(providersRes.data);
    } catch {
      message.error('获取设置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleToggleDebug = async (checked: boolean) => {
    setSaving(true);
    try {
      const { data } = await updateSettings({ debug_mode: checked });
      setSettings(data);
      message.success(checked ? '调试模式已开启' : '调试模式已关闭');
    } catch {
      message.error('保存设置失败');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleHeadless = async (checked: boolean) => {
    setSaving(true);
    try {
      const { data } = await updateSettings({ headless_mode: checked });
      setSettings(data);
      message.success(checked ? '无头模式已开启' : '无头模式已关闭');
    } catch {
      message.error('保存设置失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, flex: 1, overflowY: 'auto' }}>
      {/* 调试模式 */}
      <Card
        title={
          <Space>
            <BugOutlined />
            <span>调试模式</span>
            {settings?.debug_mode && (
              <Tag color="orange">已开启</Tag>
            )}
          </Space>
        }
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}
        >
          <div>
            <Text strong style={{ fontSize: 15 }}>
              启用调试模式
            </Text>
            <Paragraph
              type="secondary"
              style={{ marginBottom: 0, marginTop: 4 }}
            >
              开启后，自动化操作的每个步骤都会截图并记录详细日志
            </Paragraph>
          </div>
          <Switch
            checked={settings?.debug_mode}
            onChange={handleToggleDebug}
            loading={saving}
          />
        </div>

        <Divider style={{ margin: '12px 0' }} />

        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text type="secondary">
            <CameraOutlined style={{ marginRight: 6 }} />
            开启后每个步骤自动截图保存 (失败时无论是否开启都会截图)
          </Text>
          <Text type="secondary">
            <FileTextOutlined style={{ marginRight: 6 }} />
            保存每个步骤的页面 HTML 源码和可访问性快照
          </Text>
        </Space>

        {settings?.debug_mode && (
          <Alert
            style={{ marginTop: 16 }}
            type="warning"
            showIcon
            message="调试模式已开启"
            description="调试模式会产生大量截图和日志文件，建议仅在排查问题时开启。日志保存在 backend/.automation_logs/ 目录下。"
          />
        )}
      </Card>

      {/* 无头模式 */}
      <Card
        style={{ marginTop: 16 }}
        title={
          <Space>
            <EyeInvisibleOutlined />
            <span>无头模式</span>
            {settings?.headless_mode && (
              <Tag color="blue">已开启</Tag>
            )}
          </Space>
        }
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <Text strong style={{ fontSize: 15 }}>
              启用无头模式
            </Text>
            <Paragraph
              type="secondary"
              style={{ marginBottom: 0, marginTop: 4 }}
            >
              开启后浏览器在后台运行，不显示窗口，适合服务器环境或批量操作
            </Paragraph>
          </div>
          <Switch
            checked={settings?.headless_mode}
            onChange={handleToggleHeadless}
            loading={saving}
          />
        </div>

        {settings?.headless_mode && (
          <Alert
            style={{ marginTop: 16 }}
            type="info"
            showIcon
            message="无头模式已开启"
            description="新启动的浏览器将在后台运行，不会弹出窗口。已运行的浏览器不受影响，需重新启动才会生效。"
          />
        )}
      </Card>

      {/* 默认接码提供商 */}
      <Card
        style={{ marginTop: 16 }}
        title={
          <Space>
            <PhoneOutlined />
            <span>默认接码提供商</span>
          </Space>
        }
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <Text strong style={{ fontSize: 15 }}>
              选择默认提供商
            </Text>
            <Paragraph
              type="secondary"
              style={{ marginBottom: 0, marginTop: 4 }}
            >
              自动接码验证时使用的提供商，需先在「接码管理」中添加
            </Paragraph>
          </div>
          <Select
            style={{ width: 200 }}
            placeholder="选择提供商"
            value={settings?.default_sms_provider_id || undefined}
            onChange={async (val) => {
              setSaving(true);
              try {
                const { data } = await updateSettings({ default_sms_provider_id: val || '' });
                setSettings(data);
                message.success('已保存');
              } catch {
                message.error('保存失败');
              } finally {
                setSaving(false);
              }
            }}
            loading={saving}
            allowClear
            options={providers.map((p) => ({ value: String(p.id), label: p.name }))}
          />
        </div>
      </Card>
    </div>
  );
};

export default SettingsPage;
