import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import { User, Landmark } from 'lucide-react';
import type { CompanyData } from '@/services/types';

const PersonNode = ({ data }: NodeProps<CompanyData>) => {
  const isInvestor = data.type === 'Investor';
  
  return (
    <div className={`relative flex items-center gap-2 px-3 py-2 rounded-full border-2 shadow-sm transition-all hover:shadow-md ${
      isInvestor 
        ? 'bg-accent-info-soft border-accent-info text-accent-info' 
        : 'bg-indigo-50 border-indigo-300 text-indigo-800'
    }`}>
      {/* Handles for Force Graph connectivity */}
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />

      <div className={`p-1 rounded-full ${isInvestor ? 'bg-accent-info-soft' : 'bg-indigo-200'}`}>
        {isInvestor ? <Landmark size={14} /> : <User size={14} />}
      </div>
      
      <div className="flex flex-col">
        <span className="text-xs font-bold leading-none">{data.label}</span>
        <span className="text-[8px] opacity-70 uppercase tracking-wide leading-none mt-0.5">
          {isInvestor ? 'Global Investor' : 'Board Member'}
        </span>
      </div>
    </div>
  );
};

export default memo(PersonNode);

