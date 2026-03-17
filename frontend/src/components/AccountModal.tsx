import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Select, message, Divider } from 'antd';
import {
  MailOutlined,
  LockOutlined,
  SafetyOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import {
  createAccount,
  updateAccount,
  getTags,
} from '@/api';
import type { Account } from '@/types';

const { TextArea } = Input;

interface AccountModalProps {
  visible: boolean;
  account: Account | null;
  onClose: () => void;
  onSuccess: () => void;
}

const AccountModal: React.FC<AccountModalProps> = ({
  visible,
  account,
  onClose,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [allTags, setAllTags] = useState<string[]>([]);

  useEffect(() => {
    if (visible) {
      loadTags();
      if (account) {
        const formValues = {
          ...account,
          tags: account.tags ? account.tags.split(',').map((t) => t.trim()) : [],
        };
        form.setFieldsValue(formValues);
      } else {
        form.resetFields();
      }
    }
  }, [visible, account]);

  const loadTags = async () => {
    try {
      const { data } = await getTags();
      setAllTags(data.tags);
    } catch (error) {
      console.error('加载标签失败:', error);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const submitValues = {
        ...values,
        tags: Array.isArray(values.tags) ? values.tags.join(', ') : values.tags || '',
      };

      if (account) {
        // 保留原有的 family_group_id，避免编辑账号时把分组关联清掉
        submitValues.group_id = account.family_group_id ?? null;
        await updateAccount(account.id, submitValues);
        message.success('账号更新成功');
      } else {
        await createAccount(submitValues);
        message.success('账号添加成功');
      }

      onSuccess();
      onClose();
    } catch (error: any) {
      if (error.response) {
        message.error(error.response.data.detail || '保存失败');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={account ? '编辑账号' : '添加账号'}
      open={visible}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      width={520}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        style={{ marginTop: 16 }}
        requiredMark={false}
      >
        <Form.Item
          name="email"
          label="邮箱地址"
          rules={[{ required: true, message: '请输入邮箱地址' }]}
        >
          <Input
            prefix={<MailOutlined style={{ color: '#bfbfbf' }} />}
            placeholder="example@gmail.com"
          />
        </Form.Item>

        <Form.Item
          name="password"
          label="密码"
        >
          <Input.Password
            prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
            placeholder="账号密码"
          />
        </Form.Item>

        <Form.Item name="recovery_email" label="辅助邮箱">
          <Input
            prefix={<MailOutlined style={{ color: '#bfbfbf' }} />}
            placeholder="用于账号恢复"
          />
        </Form.Item>

        <Form.Item name="totp_secret" label="2FA 密钥">
          <Input
            prefix={<SafetyOutlined style={{ color: '#bfbfbf' }} />}
            placeholder="如: JBSWY3DPEHPK3PXP"
          />
        </Form.Item>

        <Divider style={{ margin: '8px 0 16px' }} />

        <Form.Item name="group_name" label="分组">
          <Input
            prefix={<FolderOutlined style={{ color: '#bfbfbf' }} />}
            placeholder="如: 工作、个人"
          />
        </Form.Item>

        <Form.Item name="tags" label="标签">
          <Select
            mode="tags"
            style={{ width: '100%' }}
            placeholder="选择或输入标签，按回车添加"
            tokenSeparators={[',']}
            options={allTags.map((tag) => ({ label: tag, value: tag }))}
          />
        </Form.Item>

        <Form.Item name="notes" label="备注">
          <TextArea rows={3} placeholder="其他信息..." />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default AccountModal;
