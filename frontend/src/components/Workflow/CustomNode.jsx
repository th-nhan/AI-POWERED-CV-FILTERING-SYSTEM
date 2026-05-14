import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import * as Icons from 'lucide-react';

const CustomNode = ({ data, isConnectable }) => {
  const IconComponent = Icons[data.icon] || Icons.HelpCircle;

  // status can be 'pending', 'processing', 'done'
  const isProcessing = data.status === 'processing';
  const isDone = data.status === 'done';

  const statusColors = {
    pending: 'bg-gray-100 border-gray-300 text-gray-500',
    processing: 'bg-yellow-50 border-yellow-400 text-yellow-600',
    done: 'bg-green-50 border-green-500 text-green-600'
  };

  return (
    <div className={`relative flex items-center p-4 rounded-xl shadow-md border-2 w-64 bg-white transition-all duration-300 ${isProcessing ? 'border-yellow-400 shadow-yellow-200 scale-105 z-50' : isDone ? 'border-green-500 shadow-green-100 z-10' : 'border-gray-200 z-10'}`}>
      {/* Top / Bottom Handles for Loop */}
      <Handle type="target" position={Position.Bottom} id="bottom-target" isConnectable={isConnectable} className="w-2 h-2 opacity-0" />
      <Handle type="source" position={Position.Bottom} id="bottom-source" isConnectable={isConnectable} className="w-2 h-2 opacity-0" />

      {/* Main Flow Handles */}
      <Handle type="target" position={Position.Left} id="left" isConnectable={isConnectable} className={`w-3 h-3 ${isDone ? 'bg-green-500' : isProcessing ? 'bg-yellow-500' : 'bg-gray-300'}`} />
      
      {/* Icon Container */}
      <div className={`p-3 rounded-full mr-4 transition-colors duration-300 ${statusColors[data.status]}`}>
        <IconComponent size={24} />
      </div>

      {/* Content */}
      <div className="flex-col flex-1">
        <div className="font-bold text-gray-800 text-sm">{data.label}</div>
        <div className="text-xs text-gray-500 capitalize">{data.status}</div>
      </div>

      {/* Status Indicator */}
      <div className="absolute top-[-6px] right-[-6px] w-4 h-4">
        {isProcessing && (
          <span className="absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75 animate-ping"></span>
        )}
        <span className={`relative inline-flex rounded-full h-4 w-4 border-2 border-white ${isDone ? 'bg-green-500' : isProcessing ? 'bg-yellow-400' : 'bg-gray-300'}`}></span>
      </div>

      <Handle type="source" position={Position.Right} id="right" isConnectable={isConnectable} className={`w-3 h-3 ${isDone ? 'bg-green-500' : isProcessing ? 'bg-yellow-500' : 'bg-gray-300'}`} />
    </div>
  );
};

export default memo(CustomNode);
