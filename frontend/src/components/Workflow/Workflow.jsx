import React, { useState, useCallback, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

import CustomNode from './CustomNode';
import { initialNodes } from './nodes';
import { initialEdges } from './edges';

const nodeTypes = {
  custom: CustomNode,
};

const Workflow = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  
  const [isRunning, setIsRunning] = useState(false);
  const [cvCount, setCvCount] = useState(0);   // set by event, 0 = not started
  const [currentCV, setCurrentCV] = useState(0);
  
  // Refs for tracking simulation state across timeouts
  const timeoutsRef = useRef([]);

  const resetWorkflow = useCallback(() => {
    // Clear all timeouts
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
    
    // Reset nodes to pending
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...n.data, status: 'pending' },
      }))
    );
    
    // Reset edges to not animated
    setEdges((eds) =>
      eds.map((e) => ({
        ...e,
        animated: false,
      }))
    );
    
    setIsRunning(false);
    setCurrentCV(0);
  }, [setNodes, setEdges]);

  const updateNodeStatus = useCallback((nodeId, status) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === nodeId) {
          return { ...n, data: { ...n.data, status } };
        }
        return n;
      })
    );
  }, [setNodes]);

  const updateEdgeStatus = useCallback((sourceId, targetId, animated) => {
    setEdges((eds) =>
      eds.map((e) => {
        if (e.source === sourceId && e.target === targetId) {
          return { ...e, animated };
        }
        return e;
      })
    );
  }, [setEdges]);

  const simulateWorkflow = useCallback((totalCVs) => {
    if (isRunning) return;
    
    resetWorkflow();
    setIsRunning(true);
    setCurrentCV(1);

    const delays = {
      '1': 1000, // JD
      '2': 1000, // Trigger CV
      '3': 1500, // Extract Text
      '4': 2000, // AI Engine
      '5': 1500, // Hybrid Scoring
      '6': 1000, // Output
    };

    let currentTime = 0;

    const scheduleTask = (fn, delay) => {
      const id = setTimeout(fn, delay);
      timeoutsRef.current.push(id);
    };

    // Schedule CV 1 (Nodes 1 to 6)
    const firstSeq = ['1', '2', '3', '4', '5', '6'];
    firstSeq.forEach((nodeId, index) => {
      scheduleTask(() => {
        setCurrentCV(1);
        updateNodeStatus(nodeId, 'processing');
        if (index > 0) updateEdgeStatus(firstSeq[index - 1], nodeId, true);
      }, currentTime);

      currentTime += delays[nodeId];

      scheduleTask(() => {
        updateNodeStatus(nodeId, 'done');
        if (index > 0) updateEdgeStatus(firstSeq[index - 1], nodeId, false);
      }, currentTime);
    });

    // Schedule CV 2 to totalCVs (Nodes 3 to 6)
    for (let cvIndex = 2; cvIndex <= totalCVs; cvIndex++) {
      scheduleTask(() => {
        ['3', '4', '5', '6'].forEach(id => updateNodeStatus(id, 'pending'));
      }, currentTime);
      
      currentTime += 500;

      const loopSeq = ['3', '4', '5', '6'];
      loopSeq.forEach((nodeId, index) => {
        scheduleTask(() => {
          setCurrentCV(cvIndex);
          updateNodeStatus(nodeId, 'processing');
          if (index > 0) updateEdgeStatus(loopSeq[index - 1], nodeId, true);
        }, currentTime);

        currentTime += delays[nodeId];

        scheduleTask(() => {
          updateNodeStatus(nodeId, 'done');
          if (index > 0) updateEdgeStatus(loopSeq[index - 1], nodeId, false);
        }, currentTime);
      });
    }

    // All done
    scheduleTask(() => {
      setIsRunning(false);
    }, currentTime + 500);

  }, [isRunning, resetWorkflow, updateNodeStatus, updateEdgeStatus]);

  // Listen for trigger — read count from event.detail
  React.useEffect(() => {
    const handleTrigger = (e) => {
      const count = e.detail?.count;
      if (count && count > 0) {
        setCvCount(count);
        simulateWorkflow(count);
      } else {
        simulateWorkflow(cvCount || 1);
      }
    };
    window.addEventListener('triggerWorkflow', handleTrigger);
    
    return () => {
      window.removeEventListener('triggerWorkflow', handleTrigger);
    };
  }, [simulateWorkflow, cvCount]);

  // Clean up timeouts ONLY on unmount
  React.useEffect(() => {
    return () => {
      timeoutsRef.current.forEach(clearTimeout);
    };
  }, []);

  return (
    <div className="w-full h-[600px] flex flex-col bg-slate-50 font-sans relative border border-slate-200 rounded-3xl overflow-hidden shadow-sm mt-6">
      {/* Header Panel */}
      <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-50 bg-white px-6 py-4 rounded-2xl shadow-lg border border-slate-200 flex items-center space-x-6">
        <div>
          <h1 className="text-xl font-bold text-slate-800">CV Filtering Workflow</h1>
          <p className="text-sm text-slate-500">Real-time AI Pipeline Simulation</p>
        </div>
        
        <div className="h-10 w-px bg-slate-200"></div>

        <div className="flex items-center space-x-4">
          {cvCount > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium text-slate-500">Tổng CV:</span>
              <span className="text-sm font-bold text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-lg border border-indigo-100">{cvCount}</span>
            </div>
          )}
          
          <button
            onClick={resetWorkflow}
            className="px-4 py-2 rounded-lg font-semibold text-slate-600 bg-white border border-slate-300 hover:bg-slate-50 transition-all shadow-sm active:scale-95"
          >
            Reset Flow
          </button>
        </div>
      </div>

      {/* Status Badge */}
      {isRunning && (
        <div className="absolute top-24 left-1/2 transform -translate-x-1/2 z-50 animate-bounce">
          <div className="bg-yellow-100 border border-yellow-400 text-yellow-800 px-4 py-2 rounded-full shadow-md font-semibold flex items-center space-x-2">
             <span className="relative flex h-3 w-3">
               <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-500 opacity-75"></span>
               <span className="relative inline-flex rounded-full h-3 w-3 bg-yellow-500"></span>
             </span>
             <span>Đang xử lý CV: {currentCV} / {cvCount}</span>
          </div>
        </div>
      )}

      {/* React Flow Canvas */}
      <div className="flex-1 w-full h-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-right"
          className="bg-slate-50"
          nodesDraggable={true}
          nodesConnectable={false}
          elementsSelectable={true}
          zoomOnScroll={true}
          panOnDrag={true}
          zoomOnDoubleClick={true}
          panOnScroll={false}
          minZoom={0.3}
          maxZoom={2}
        >
          <Background color="#cbd5e1" gap={20} size={1} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeColor={(n) => {
              const s = n.data?.status;
              if (s === 'done') return '#10b981';
              if (s === 'processing') return '#f59e0b';
              return '#cbd5e1';
            }}
            maskColor="rgba(248,250,252,0.7)"
            style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8 }}
          />
        </ReactFlow>
      </div>
    </div>
  );
};

export default Workflow;
