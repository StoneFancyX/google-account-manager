import React, { useState, useEffect, useRef } from 'react';
import { Typography, Progress, message, Tooltip, Flex } from 'antd';
import { getTOTP } from '@/api';

const { Text } = Typography;

interface TOTPDisplayProps {
  accountId: number;
}

const TOTPDisplay: React.FC<TOTPDisplayProps> = ({ accountId }) => {
  const [totp, setTotp] = useState({ code: '------', remaining: 30, formatted: '--- ---' });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadTOTP();
    intervalRef.current = setInterval(loadTOTP, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [accountId]);

  const loadTOTP = async () => {
    try {
      const { data } = await getTOTP(accountId);
      setTotp(data);
    } catch {
      // silently ignore
    }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(totp.code).then(() => {
      message.success('验证码已复制');
    });
  };

  const percent = (totp.remaining / 30) * 100;
  const isUrgent = totp.remaining <= 10;
  const color = isUrgent ? '#ff4d4f' : '#4285f4';

  return (
    <Tooltip title="点击复制验证码">
      <Flex
        align="center"
        gap={6}
        onClick={copyCode}
        style={{ cursor: 'pointer', userSelect: 'none' }}
      >
        <Progress
          type="circle"
          percent={percent}
          size={22}
          strokeColor={color}
          trailColor="#f0f0f0"
          format={() => ''}
          strokeWidth={4}
        />
        <Text
          strong
          style={{
            fontFamily: "'SF Mono', Consolas, monospace",
            fontSize: 14,
            color,
            transition: 'color 0.3s',
          }}
        >
          {totp.formatted}
        </Text>
      </Flex>
    </Tooltip>
  );
};

export default TOTPDisplay;
