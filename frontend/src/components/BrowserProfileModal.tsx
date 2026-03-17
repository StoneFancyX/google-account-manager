import React, { useEffect } from 'react';
import {
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Divider,
  message,
} from 'antd';
import type { BrowserProfile } from '@/api/browser';
import { createBrowserProfile, updateBrowserProfile } from '@/api';

interface Props {
  open: boolean;
  profile: BrowserProfile | null;
  accounts: { id: number; email: string }[];
  onClose: () => void;
  onSuccess: () => void;
}

const TIMEZONE_OPTIONS = [
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Seoul',
  'Asia/Singapore',
  'America/New_York',
  'America/Los_Angeles',
  'America/Chicago',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Australia/Sydney',
  'Pacific/Auckland',
];

const RESOLUTION_PRESETS = [
  { label: '1920x1080 (Full HD)', width: 1920, height: 1080 },
  { label: '2560x1440 (2K)', width: 2560, height: 1440 },
  { label: '1366x768', width: 1366, height: 768 },
  { label: '1440x900', width: 1440, height: 900 },
  { label: '1536x864', width: 1536, height: 864 },
  { label: '2560x1600 (MacBook)', width: 2560, height: 1600 },
];

const BrowserProfileModal: React.FC<Props> = ({
  open,
  profile,
  accounts,
  onClose,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const isEdit = !!profile;

  useEffect(() => {
    if (open) {
      if (profile) {
        form.setFieldsValue(profile);
      } else {
        form.resetFields();
      }
    }
  }, [open, profile, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      if (isEdit) {
        await updateBrowserProfile(profile!.id, values);
        message.success('配置已更新');
      } else {
        await createBrowserProfile(values);
        message.success('配置已创建');
      }
      onSuccess();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    }
  };

  const handleResolutionPreset = (value: string) => {
    const preset = RESOLUTION_PRESETS.find((p) => p.label === value);
    if (preset) {
      form.setFieldsValue({
        screen_width: preset.width,
        screen_height: preset.height,
      });
    }
  };

  return (
    <Modal
      title={isEdit ? '编辑浏览器配置' : '新建浏览器配置'}
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      width={600}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          os_type: 'macos',
          language: 'en-US',
          screen_width: 1920,
          screen_height: 1080,
          webrtc_disabled: true,
          proxy_type: '',
        }}
      >
        <Form.Item
          name="name"
          label="配置名称"
          rules={[{ required: true, message: '请输入名称' }]}
        >
          <Input placeholder="例如: 工作号、个人号" />
        </Form.Item>

        <Form.Item name="account_id" label="关联账号">
          <Select
            placeholder="选择关联的 Google 账号"
            allowClear
            showSearch
            optionFilterProp="label"
            options={accounts.map((a) => ({ value: a.id, label: a.email }))}
          />
        </Form.Item>

        <Divider>代理设置</Divider>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr 1fr', gap: 12 }}>
          <Form.Item name="proxy_type" label="类型" style={{ marginBottom: 12 }}>
            <Select
              placeholder="类型"
              allowClear
              options={[
                { value: '', label: '不使用' },
                { value: 'http', label: 'HTTP' },
                { value: 'socks5', label: 'SOCKS5' },
              ]}
            />
          </Form.Item>
          <Form.Item name="proxy_host" label="地址" style={{ marginBottom: 12 }}>
            <Input placeholder="127.0.0.1" />
          </Form.Item>
          <Form.Item name="proxy_port" label="端口" style={{ marginBottom: 12 }}>
            <InputNumber placeholder="7890" style={{ width: '100%' }} />
          </Form.Item>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Form.Item name="proxy_username" label="用户名" style={{ marginBottom: 12 }}>
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="proxy_password" label="密码" style={{ marginBottom: 12 }}>
            <Input.Password placeholder="可选" />
          </Form.Item>
        </div>

        <Divider>指纹配置</Divider>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Form.Item name="os_type" label="操作系统">
            <Select
              options={[
                { value: 'macos', label: 'macOS' },
                { value: 'windows', label: 'Windows' },
                { value: 'linux', label: 'Linux' },
              ]}
            />
          </Form.Item>
          <Form.Item name="language" label="语言">
            <Select
              showSearch
              options={[
                { value: 'zh-CN', label: '中文 (zh-CN)' },
                { value: 'en-US', label: 'English (en-US)' },
                { value: 'ja-JP', label: '日本語 (ja-JP)' },
                { value: 'ko-KR', label: '한국어 (ko-KR)' },
                { value: 'fr-FR', label: 'Francais (fr-FR)' },
                { value: 'de-DE', label: 'Deutsch (de-DE)' },
              ]}
            />
          </Form.Item>
        </div>

        <Form.Item name="timezone" label="时区">
          <Select
            placeholder="自动 (跟随代理 IP)"
            allowClear
            showSearch
            options={TIMEZONE_OPTIONS.map((tz) => ({ value: tz, label: tz }))}
          />
        </Form.Item>

        <div style={{ marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: '#666' }}>分辨率预设:</span>{' '}
          <Select
            size="small"
            placeholder="选择预设"
            style={{ width: 220, marginLeft: 8 }}
            onChange={handleResolutionPreset}
            options={RESOLUTION_PRESETS.map((p) => ({ value: p.label, label: p.label }))}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Form.Item name="screen_width" label="宽度">
            <InputNumber style={{ width: '100%' }} min={800} max={3840} />
          </Form.Item>
          <Form.Item name="screen_height" label="高度">
            <InputNumber style={{ width: '100%' }} min={600} max={2160} />
          </Form.Item>
        </div>

        <Form.Item name="user_agent" label="User-Agent">
          <Input.TextArea
            placeholder="留空则自动生成 (推荐)"
            rows={2}
          />
        </Form.Item>

        <Form.Item name="webrtc_disabled" label="禁用 WebRTC" valuePropName="checked">
          <Switch checkedChildren="已禁用" unCheckedChildren="已启用" />
        </Form.Item>

        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} placeholder="可选" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default BrowserProfileModal;
