# Intelligent Alert Review Agent - Design Document

## Executive Summary

An AI-powered alert triage and remediation system that monitors ServiceNow alerts for VMware infrastructure, leverages Dynatrace telemetry for deep analysis, and executes remediation through Ansible Tower workflows. The system reduces MTTA/MTTR while maintaining healthcare compliance and safety standards.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ServiceNow ITSM                             │
│                    (Alert Source & Orchestration)                    │
├─────────────────────────────────────────────────────────────────────┤
│  • Event Management  • Incident Records  • CMDB Integration         │
│  • Change Records    • Maintenance Windows  • SLA Tracking          │
└────────────────────────────┬────────────────────────────────────────┘
                             │ REST API / Webhooks
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Alert Intelligence Agent                          │
│                      (AI Analysis Engine)                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │           Alert Ingestion & Normalization                   │   │
│  │  • ServiceNow Event Parser                                  │   │
│  │  • CMDB Asset Enrichment                                    │   │
│  │  • Alert Deduplication & Correlation                        │   │
│  └────────────────────────┬───────────────────────────────────┘   │
│                           │                                          │
│  ┌────────────────────────▼───────────────────────────────────┐   │
│  │           Context Gathering Engine                          │   │
│  │                                                              │   │
│  │  Dynatrace API ─────┐                                       │   │
│  │  • VM Metrics       │                                       │   │
│  │  • Process Analysis │                                       │   │
│  │  • Problem Detection├──► Unified Context                    │   │
│  │  • Topology Map     │         Model                         │   │
│  │                     │                                       │   │
│  │  ServiceNow CMDB ───┤                                       │   │
│  │  • Asset Info       │                                       │   │
│  │  • Relationships    │                                       │   │
│  │  • Change History   │                                       │   │
│  │                     │                                       │   │
│  │  Historical DB ─────┘                                       │   │
│  │  • Past Incidents                                           │   │
│  │  • Resolution Patterns                                      │   │
│  └────────────────────────┬───────────────────────────────────┘   │
│                           │                                          │
│  ┌────────────────────────▼───────────────────────────────────┐   │
│  │              AI Analysis & Decision Engine                  │   │
│  │                                                              │   │
│  │  Pattern Recognition:                                       │   │
│  │  • Time-series trend analysis                               │   │
│  │  • Anomaly detection                                        │   │
│  │  • Correlation with infrastructure events                   │   │
│  │                                                              │   │
│  │  Root Cause Hypothesis:                                     │   │
│  │  • Claude Sonnet 4.5 LLM reasoning                         │   │
│  │  • Vector similarity search (past incidents)                │   │
│  │  • Dynatrace Davis AI integration                           │   │
│  │                                                              │   │
│  │  Impact Assessment:                                         │   │
│  │  • critical vs non-critical classification                  │   │
│  │  • Service dependency mapping                               │   │
│  │  • Business impact scoring                                  │   │
│  └────────────────────────┬───────────────────────────────────┘   │
│                           │                                          │
│  ┌────────────────────────▼───────────────────────────────────┐   │
│  │           Recommendation Engine                             │   │
│  │                                                              │   │
│  │  Decision Matrix:                                           │   │
│  │  • Auto-remediate (safe, proven actions)                    │   │
│  │  • Guided remediation (present runbook + context)           │   │
│  │  • Escalate (page engineer with analysis)                   │   │
│  │                                                              │   │
│  │  Playbook Selection:                                        │   │
│  │  • Match to Ansible Tower job templates                     │   │
│  │  • Verify pre-requisites and safety checks                  │   │
│  │  • Calculate confidence score                               │   │
│  └────────────────────────┬───────────────────────────────────┘   │
│                           │                                          │
└───────────────────────────┼──────────────────────────────────────┘
                            │
          ┌─────────────────┴─────────────────┐
          │                                    │
          ▼                                    ▼
┌──────────────────────┐           ┌──────────────────────┐
│   Ansible Tower      │           │   ServiceNow         │
│                      │           │                      │
│  • Execute Playbooks │           │  • Update Incident   │
│  • Job Scheduling    │           │  • Create Work Notes │
│  • Approval Workflow │           │  • Trigger Workflows │
│  • Audit Logging     │           │  • Notify Stakeholders│
└──────────────────────┘           └──────────────────────┘
```

## Component Details

### 1. Alert Ingestion Layer

**ServiceNow Integration**

```python
# ServiceNow Event Table Query
class ServiceNowEventMonitor:
    def __init__(self, instance_url, credentials):
        self.snow_client = ServiceNowClient(instance_url, credentials)
        
    def poll_events(self, filters):
        """
        Poll ServiceNow Event [em_event] table
        Filter: state=Ready, type in [CPU, Memory, Storage]
        """
        query = {
            'sysparm_query': 'state=Ready^type=VM Alert^ORDERBYDESCsys_created_on',
            'sysparm_limit': 100
        }
        return self.snow_client.get('em_event', params=query)
    
    def enrich_with_cmdb(self, event):
        """
        Lookup CI details from CMDB
        Tables: cmdb_ci_vmware_instance, cmdb_ci_server
        """
        ci_sys_id = event['cmdb_ci']
        ci_data = self.snow_client.get(f'cmdb_ci/{ci_sys_id}')
        
        return {
            **event,
            'vm_name': ci_data['name'],
            'datacenter': ci_data['u_datacenter'],
            'environment': ci_data['u_environment'],
            'application': ci_data['u_application'],
            'support_group': ci_data['support_group'],
            'business_service': ci_data['business_service'],
            'is_critical': ci_data['u_critical_system']
        }
```

**Alert Normalization Schema**

```yaml
normalized_alert:
  metadata:
    alert_id: "EVT0012345"
    source: "ServiceNow"
    received_at: "2024-02-08T14:30:00Z"
    severity: "warning|major|critical"
    
  resource:
    vm_name: "prdapp01.company.local"
    vm_uuid: "42056e8c-1234-5678-90ab-cdef12345678"
    datacenter: "DC-PITTSBURGH-01"
    cluster: "PROD-CLUSTER-03"
    environment: "production"
    
  metric:
    type: "cpu|memory|storage"
    current_value: 87.5
    threshold_warning: 75.0
    threshold_critical: 90.0
    unit: "percent"
    
  context:
    application: "Epic EMR - Application Server"
    business_service: "Electronic Health Records"
    support_group: "Infrastructure - VMware Team"
    is_critical: true
    sla_tier: "tier1"
    
  timeline:
    first_occurrence: "2024-02-08T13:15:00Z"
    last_occurrence: "2024-02-08T14:30:00Z"
    event_count: 15
    trend: "escalating|stable|improving"
```

### 2. Context Gathering Engine

**Dynatrace Integration**

```python
class DynatraceContextGatherer:
    def __init__(self, tenant_url, api_token):
        self.dt_client = DynatraceClient(tenant_url, api_token)
    
    def gather_vm_context(self, vm_name, alert_time):
        """
        Gather comprehensive context from Dynatrace
        """
        # Find VM entity in Dynatrace
        entity = self.dt_client.entities.query(
            entity_selector=f'type("HOST"),entityName.equals("{vm_name}")'
        )
        
        entity_id = entity[0]['entityId']
        
        context = {
            'metrics': self._get_timeseries_metrics(entity_id, alert_time),
            'processes': self._get_process_analysis(entity_id),
            'problems': self._get_related_problems(entity_id),
            'dependencies': self._get_service_dependencies(entity_id),
            'events': self._get_recent_events(entity_id),
            'davis_analysis': self._get_davis_insights(entity_id)
        }
        
        return context
    
    def _get_timeseries_metrics(self, entity_id, alert_time):
        """
        Retrieve 4-hour window of metrics around alert
        """
        metrics = [
            'builtin:host.cpu.usage',
            'builtin:host.mem.usage',
            'builtin:host.disk.usedPct',
            'builtin:host.disk.bytesRead',
            'builtin:host.disk.bytesWritten'
        ]
        
        data = {}
        for metric in metrics:
            result = self.dt_client.metrics.query(
                metric_selector=metric,
                entity_selector=f'entityId("{entity_id}")',
                from_timestamp=alert_time - timedelta(hours=2),
                to_timestamp=alert_time + timedelta(hours=2),
                resolution='1m'
            )
            data[metric] = result
            
        return data
    
    def _get_process_analysis(self, entity_id):
        """
        Identify top CPU/Memory consuming processes
        """
        processes = self.dt_client.processes.list(
            host_id=entity_id,
            fields='+consumedHostCpu,+consumedHostMem'
        )
        
        # Sort by resource consumption
        sorted_processes = sorted(
            processes, 
            key=lambda x: x['consumedHostCpu'], 
            reverse=True
        )
        
        return sorted_processes[:10]
    
    def _get_related_problems(self, entity_id):
        """
        Check if Dynatrace Davis AI detected related problems
        """
        problems = self.dt_client.problems.list(
            entity_selector=f'entityId("{entity_id}")',
            from_timestamp=datetime.now() - timedelta(hours=24),
            problem_selector='status("OPEN")'
        )
        
        return problems
    
    def _get_davis_insights(self, entity_id):
        """
        Leverage Dynatrace Davis AI root cause analysis
        """
        problems = self._get_related_problems(entity_id)
        
        insights = []
        for problem in problems:
            detail = self.dt_client.problems.get(problem['problemId'])
            insights.append({
                'problem_id': problem['problemId'],
                'title': problem['title'],
                'root_cause': detail['rootCauseEntity'],
                'affected_entities': detail['affectedEntities'],
                'davis_analysis': detail['evidenceDetails']
            })
            
        return insights
```

**Historical Pattern Analysis**

```python
class HistoricalPatternMatcher:
    def __init__(self, vector_db):
        self.vector_db = vector_db  # Pinecone or ChromaDB
        
    def find_similar_incidents(self, current_alert):
        """
        Vector similarity search for past incidents
        """
        # Create embedding of current situation
        embedding = self._create_alert_embedding(current_alert)
        
        # Search vector DB
        similar = self.vector_db.query(
            vector=embedding,
            top_k=5,
            filter={
                'resource_type': 'vm',
                'metric_type': current_alert['metric']['type'],
                'resolution_successful': True
            }
        )
        
        return similar
    
    def _create_alert_embedding(self, alert):
        """
        Create semantic embedding of alert context
        """
        context_text = f"""
        Alert Type: {alert['metric']['type']}
        Severity: {alert['metadata']['severity']}
        Application: {alert['context']['application']}
        Trend: {alert['timeline']['trend']}
        Environment: {alert['resource']['environment']}
        
        Dynatrace Context:
        - Top Process: {alert['dynatrace']['processes'][0]['name']}
        - Recent Changes: {alert['servicenow']['recent_changes']}
        - Related Problems: {alert['dynatrace']['problems']}
        """
        
        # Use Claude or OpenAI embeddings API
        return self.embedding_model.encode(context_text)
```

### 3. AI Analysis Engine

**Decision Logic**

```python
class AlertAnalyzer:
    def __init__(self, llm_client):
        self.llm = llm_client  # Claude Sonnet 4.5
        
    def analyze_alert(self, enriched_alert):
        """
        AI-powered root cause analysis and recommendation
        """
        # Construct comprehensive prompt
        analysis_prompt = self._build_analysis_prompt(enriched_alert)
        
        # Call Claude for reasoning
        response = self.llm.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            temperature=0.1,  # Low temperature for consistency
            system=self._get_system_prompt(),
            messages=[{
                "role": "user",
                "content": analysis_prompt
            }]
        )
        
        # Parse structured response
        analysis = self._parse_llm_response(response.content[0].text)
        
        return analysis
    
    def _get_system_prompt(self):
        return """You are an expert infrastructure engineer specializing in VMware 
        environments in healthcare settings. Your role is to analyze alerts from 
        ServiceNow, correlate with Dynatrace telemetry, and provide actionable 
        remediation recommendations.
        
        When analyzing alerts:
        1. Consider the critical impact - patient care systems take absolute priority
        2. Review historical patterns and similar incidents
        3. Leverage Dynatrace Davis AI insights when available
        4. Propose remediation steps that can be automated via Ansible
        5. Always provide confidence scores and alternative hypotheses
        6. Respect maintenance windows for non-emergency changes
        
        Respond in JSON format with the following structure:
        {
            "confidence_score": 0.0-1.0,
            "root_cause_primary": "...",
            "root_cause_alternatives": [...],
            "severity_assessment": "...",
            "business_impact": "...",
            "recommended_action": "auto-remediate|guided-remediation|escalate",
            "remediation_steps": [...],
            "ansible_playbook": "...",
            "requires_approval": boolean,
            "escalation_required": boolean,
            "additional_context": "..."
        }
        """
    
    def _build_analysis_prompt(self, alert):
        similar_incidents = alert['historical_matches']
        
        prompt = f"""
        CURRENT ALERT:
        VM: {alert['resource']['vm_name']}
        Metric: {alert['metric']['type']} at {alert['metric']['current_value']}{alert['metric']['unit']}
        Threshold: Warning={alert['metric']['threshold_warning']}, Critical={alert['metric']['threshold_critical']}
        Duration: {alert['timeline']['event_count']} occurrences over {alert['timeline']['duration']}
        Trend: {alert['timeline']['trend']}
        
        APPLICATION CONTEXT:
        Application: {alert['context']['application']}
        Business Service: {alert['context']['business_service']}
        critical System: {alert['context']['is_critical']}
        Environment: {alert['resource']['environment']}
        
        DYNATRACE TELEMETRY:
        Top CPU Process: {alert['dynatrace']['processes'][0]['name']} ({alert['dynatrace']['processes'][0]['consumedHostCpu']}%)
        Active Problems: {len(alert['dynatrace']['problems'])}
        Davis AI Root Cause: {alert['dynatrace']['davis_analysis']}
        
        RECENT CHANGES (Last 72h):
        {self._format_recent_changes(alert['servicenow']['recent_changes'])}
        
        SIMILAR PAST INCIDENTS:
        {self._format_similar_incidents(similar_incidents)}
        
        AVAILABLE ANSIBLE PLAYBOOKS:
        {self._format_available_playbooks(alert['ansible']['available_playbooks'])}
        
        Analyze this situation and provide your recommendation.
        """
        
        return prompt
```

**Alert Classification Matrix**

```yaml
classification_rules:
  
  cpu_high:
    patterns:
      - name: "java_memory_leak"
        indicators:
          - process_name: "java"
          - cpu_trend: "gradual_increase"
          - duration: ">2h"
          - memory_trend: "increasing"
        confidence: 0.85
        remediation: "ansible/restart_java_service.yml"
        requires_approval: true
        
      - name: "backup_job_running"
        indicators:
          - process_name: "veeam|commvault|networker"
          - time_window: "backup_window"
          - cpu_spike: "sudden"
        confidence: 0.95
        remediation: "suppress_and_monitor"
        requires_approval: false
        
      - name: "antivirus_scan"
        indicators:
          - process_name: "mcafee|symantec|defender"
          - pattern: "regular_interval"
        confidence: 0.90
        remediation: "suppress_and_monitor"
        requires_approval: false
        
      - name: "runaway_process"
        indicators:
          - single_process_cpu: ">80%"
          - process_age: "<1h"
          - no_historical_baseline: true
        confidence: 0.75
        remediation: "ansible/investigate_and_kill_process.yml"
        requires_approval: true
        
  memory_high:
    patterns:
      - name: "memory_leak"
        indicators:
          - memory_trend: "linear_increase"
          - duration: ">4h"
          - no_memory_freed: true
        confidence: 0.80
        remediation: "ansible/schedule_service_restart.yml"
        requires_approval: true
        
      - name: "legitimate_load"
        indicators:
          - memory_increase: "correlates_with_user_load"
          - within_expected_bounds: true
        confidence: 0.70
        remediation: "recommend_capacity_review"
        requires_approval: false
        
      - name: "cache_not_releasing"
        indicators:
          - process_name: "oracle|postgres|sqlserver"
          - cache_size: "at_configured_max"
        confidence: 0.85
        remediation: "ansible/flush_database_cache.yml"
        requires_approval: true
        
  storage_high:
    patterns:
      - name: "log_file_growth"
        indicators:
          - growth_location: "/var/log|C:\\Logs"
          - growth_rate: "exponential"
        confidence: 0.95
        remediation: "ansible/rotate_and_compress_logs.yml"
        requires_approval: false  # Safe automation
        
      - name: "temp_file_accumulation"
        indicators:
          - growth_location: "/tmp|C:\\Temp"
          - file_age: ">7d"
        confidence: 0.90
        remediation: "ansible/cleanup_temp_files.yml"
        requires_approval: false
        
      - name: "database_growth"
        indicators:
          - growth_location: "database_datafile_path"
          - growth_rate: "steady"
        confidence: 0.85
        remediation: "escalate_to_dba"
        requires_approval: false
        
      - name: "snapshot_accumulation"
        indicators:
          - vmware_snapshots: ">3"
          - snapshot_age: ">7d"
        confidence: 0.95
        remediation: "ansible/consolidate_snapshots.yml"
        requires_approval: true  # Data integrity risk
```

### 4. Recommendation Engine

**Output Format**

```json
{
  "analysis_id": "ANA-2024-02-08-00123",
  "timestamp": "2024-02-08T14:35:22Z",
  "alert_reference": "EVT0012345",
  
  "executive_summary": "Java application server experiencing gradual CPU increase over 3.5 hours, likely due to memory leak in application process. Dynatrace Davis AI confirms heap exhaustion pattern. Similar incident resolved 14 days ago via service restart.",
  
  "confidence_score": 0.87,
  
  "root_cause_analysis": {
    "primary_hypothesis": {
      "cause": "Memory leak in Java application (PID 8472)",
      "confidence": 0.87,
      "evidence": [
        "Gradual CPU increase correlating with heap usage growth",
        "GC overhead at 78% and increasing",
        "Dynatrace detected memory allocation anomaly",
        "No recent code deployments (last change: 23 days ago)"
      ]
    },
    "alternative_hypotheses": [
      {
        "cause": "Database connection pool exhaustion",
        "confidence": 0.45,
        "evidence": [
          "Connection pool at 95% capacity",
          "Slow query detected in application logs"
        ]
      },
      {
        "cause": "Increased legitimate user load",
        "confidence": 0.25,
        "evidence": [
          "User session count up 30% vs baseline"
        ]
      }
    ]
  },
  
  "impact_assessment": {
    "severity": "high",
    "critical_impact": true,
    "affected_services": [
      "Epic EMR - Application Tier",
      "Patient Portal Backend"
    ],
    "user_impact": "Degraded response times (avg 8.3s vs baseline 1.2s)",
    "estimated_affected_users": 450,
    "business_continuity": "Redundancy available via prdapp02, automatic failover in 5 minutes if critical threshold reached"
  },
  
  "recommended_action": {
    "action_type": "guided-remediation",
    "requires_approval": true,
    "approval_reason": "critical system - requires change approval",
    
    "immediate_steps": [
      {
        "step": 1,
        "action": "Verify backup application server health",
        "method": "ansible",
        "playbook": "check_application_server_health.yml",
        "target": "prdapp02.company.local",
        "estimated_duration": "2m",
        "auto_execute": true
      },
      {
        "step": 2,
        "action": "Capture diagnostic data",
        "method": "ansible",
        "playbook": "capture_java_diagnostics.yml",
        "parameters": {
          "pid": 8472,
          "heap_dump": true,
          "thread_dump": true
        },
        "estimated_duration": "5m",
        "auto_execute": true
      },
      {
        "step": 3,
        "action": "Restart application service",
        "method": "ansible",
        "playbook": "restart_epic_app_server.yml",
        "requires_approval": true,
        "approval_type": "change_request",
        "maintenance_window_preferred": true,
        "estimated_duration": "10m",
        "rollback_plan": "Service will auto-start, manual verification required"
      }
    ],
    
    "preventive_measures": [
      {
        "recommendation": "Increase heap size from 8GB to 12GB",
        "rationale": "Heap usage consistently above 85% during business hours",
        "effort": "medium",
        "priority": "medium"
      },
      {
        "recommendation": "Enable verbose GC logging",
        "rationale": "Improved diagnostics for future incidents",
        "effort": "low",
        "priority": "high"
      },
      {
        "recommendation": "Schedule monthly service restarts",
        "rationale": "Prevent gradual memory leak accumulation",
        "effort": "low",
        "priority": "medium"
      }
    ]
  },
  
  "ansible_integration": {
    "tower_job_template": "Epic App Server Restart - Guided",
    "job_template_id": 847,
    "inventory": "VMware Production",
    "credential": "VMware-Service-Account",
    "extra_vars": {
      "target_host": "prdapp01.company.local",
      "service_name": "epic-app-server",
      "pre_checks": true,
      "post_validation": true,
      "notification_email": "ops-team@company.com"
    },
    "approval_workflow": "CAB-Emergency-critical",
    "estimated_runtime": "15m"
  },
  
  "escalation": {
    "escalate_if_no_action_in": "20m",
    "escalation_path": [
      {
        "level": 1,
        "contact": "Infrastructure - VMware Team",
        "method": "ServiceNow Assignment"
      },
      {
        "level": 2,
        "contact": "Application Team - Epic",
        "method": "PagerDuty + Email"
      },
      {
        "level": 3,
        "contact": "Infrastructure Manager",
        "method": "Phone + PagerDuty"
      }
    ],
    "emergency_contact": {
      "condition": "CPU > 95% OR service unavailable",
      "contact": "IT Service Desk - Emergency Line",
      "phone": "+1-412-XXX-XXXX"
    }
  },
  
  "related_documentation": {
    "runbooks": [
      "RB-VMW-2847: Java Application High CPU Investigation",
      "RB-EPIC-1923: Application Server Restart Procedure"
    ],
    "knowledge_articles": [
      "KB0034521: Epic Application Memory Leak Troubleshooting",
      "KB0029384: VMware VM Performance Optimization"
    ],
    "similar_incidents": [
      {
        "incident_number": "INC0087234",
        "date": "2024-01-25",
        "resolution": "Service restart resolved issue",
        "resolution_time": "45m"
      }
    ]
  },
  
  "monitoring": {
    "watch_metrics": [
      "builtin:host.cpu.usage",
      "builtin:tech.generic.jvm.heapMemory",
      "builtin:tech.generic.jvm.gcTime"
    ],
    "alert_thresholds": {
      "cpu": "Critical if >95% for 5min",
      "heap": "Warning if >90%",
      "gc_time": "Warning if >50%"
    },
    "check_interval": "1m",
    "report_status_in": "30m"
  }
}
```

### 5. Ansible Tower Integration

**Playbook Structure**

```yaml
# playbooks/restart_epic_app_server.yml
---
- name: Guided Epic Application Server Restart
  hosts: "{{ target_host }}"
  gather_facts: yes
  
  vars:
    service_name: epic-app-server
    notification_email: ops-team@company.com
    snow_incident: "{{ snow_incident_number }}"
    
  pre_tasks:
    - name: Verify this is not the last available server
      uri:
        url: "http://loadbalancer/api/health/{{ target_host }}"
        method: GET
      register: lb_health
      delegate_to: localhost
      
    - name: Fail if no redundancy available
      fail:
        msg: "Cannot restart - no backup servers available"
      when: lb_health.json.available_servers < 2
      
    - name: Update ServiceNow incident
      servicenow.servicenow.snow_record:
        instance: "{{ snow_instance }}"
        username: "{{ snow_user }}"
        password: "{{ snow_password }}"
        state: present
        table: incident
        number: "{{ snow_incident }}"
        data:
          work_notes: "Ansible automation initiated: Pre-restart health checks passed"
      delegate_to: localhost
      
    - name: Capture pre-restart diagnostics
      include_tasks: tasks/capture_diagnostics.yml
      
    - name: Remove server from load balancer
      uri:
        url: "http://loadbalancer/api/remove/{{ target_host }}"
        method: POST
      delegate_to: localhost
      
    - name: Wait for connection draining (60 seconds)
      wait_for:
        timeout: 60
      delegate_to: localhost
  
  tasks:
    - name: Stop Epic application service
      systemd:
        name: "{{ service_name }}"
        state: stopped
      register: service_stop
      
    - name: Verify service stopped
      service_facts:
      
    - name: Clear temp files
      file:
        path: "/opt/epic/temp/*"
        state: absent
        
    - name: Start Epic application service
      systemd:
        name: "{{ service_name }}"
        state: started
      register: service_start
      
    - name: Wait for service to be healthy
      uri:
        url: "http://{{ target_host }}:8080/health"
        method: GET
        status_code: 200
      retries: 30
      delay: 10
      register: health_check
      
  post_tasks:
    - name: Add server back to load balancer
      uri:
        url: "http://loadbalancer/api/add/{{ target_host }}"
        method: POST
      delegate_to: localhost
      
    - name: Verify application functionality
      include_tasks: tasks/smoke_tests.yml
      
    - name: Capture post-restart diagnostics
      include_tasks: tasks/capture_diagnostics.yml
      
    - name: Update ServiceNow incident with success
      servicenow.servicenow.snow_record:
        instance: "{{ snow_instance }}"
        username: "{{ snow_user }}"
        password: "{{ snow_password }}"
        state: present
        table: incident
        number: "{{ snow_incident }}"
        data:
          work_notes: "Ansible automation completed successfully. Service restarted and verified healthy."
          state: 6  # Resolved
          close_code: "Solved (Permanently)"
          close_notes: "Application service restarted per AI recommendation. CPU returned to normal levels."
      delegate_to: localhost
      
    - name: Send success notification
      mail:
        host: smtp.company.com
        to: "{{ notification_email }}"
        subject: "SUCCESS: {{ target_host }} service restart completed"
        body: |
          Service restart completed successfully.
          
          Server: {{ target_host }}
          Service: {{ service_name }}
          Incident: {{ snow_incident }}
          Duration: {{ ansible_play_duration }}
          
          Post-restart health check: PASSED
          
      delegate_to: localhost
      
  rescue:
    - name: Update ServiceNow with failure
      servicenow.servicenow.snow_record:
        instance: "{{ snow_instance }}"
        table: incident
        number: "{{ snow_incident }}"
        data:
          work_notes: "ALERT: Ansible automation failed. Manual intervention required."
          urgency: 1
      delegate_to: localhost
      
    - name: Send failure notification
      mail:
        host: smtp.company.com
        to: "{{ notification_email }}"
        subject: "FAILURE: {{ target_host }} service restart failed"
        body: |
          Service restart FAILED. Manual intervention required.
          
          Server: {{ target_host }}
          Incident: {{ snow_incident }}
          Error: {{ ansible_failed_result }}
      delegate_to: localhost
      
    - name: Page on-call engineer
      uri:
        url: "https://api.pagerduty.com/incidents"
        method: POST
        headers:
          Authorization: "Token token={{ pagerduty_token }}"
          Content-Type: "application/json"
        body_format: json
        body:
          incident:
            type: "incident"
            title: "CRITICAL: Automated restart failed for {{ target_host }}"
            service:
              id: "{{ pagerduty_service_id }}"
              type: "service_reference"
            urgency: "high"
            body:
              type: "incident_body"
              details: "Ansible automation failure. Check ServiceNow {{ snow_incident }}"
      delegate_to: localhost
```

**Ansible Tower Job Templates**

```yaml
# Tower Job Template Configuration
job_templates:
  - name: "Epic App Server Restart - Guided"
    description: "AI-guided application server restart with full safety checks"
    job_type: run
    inventory: VMware Production
    project: Infrastructure Automation
    playbook: playbooks/restart_epic_app_server.yml
    credential: VMware-Service-Account
    
    extra_vars:
      snow_instance: "company.service-now.com"
      
    survey:
      - question: "Target Host"
        variable: target_host
        type: text
        required: true
        
      - question: "ServiceNow Incident Number"
        variable: snow_incident_number
        type: text
        required: true
        
      - question: "Skip Load Balancer Removal?"
        variable: skip_lb_removal
        type: multiplechoice
        choices: ["No", "Yes"]
        default: "No"
    
    ask_variables_on_launch: true
    concurrent_jobs_enabled: false
    
    notification_templates_started:
      - Slack - Ops Channel
      
    notification_templates_success:
      - ServiceNow - Auto Update
      - Email - Infrastructure Team
      
    notification_templates_error:
      - PagerDuty - Critical
      - Email - Infrastructure Manager
      - Slack - Ops Channel
      
  - name: "VM Storage Cleanup - Automated"
    description: "Automated log rotation and temp file cleanup"
    job_type: run
    playbook: playbooks/cleanup_vm_storage.yml
    
    approval_required: false  # Safe for auto-execution
    
  - name: "VM Diagnostics Capture"
    description: "Capture system diagnostics for analysis"
    job_type: run
    playbook: playbooks/capture_diagnostics.yml
    
    approval_required: false
```

### 6. ServiceNow Workflow Integration

**Incident Lifecycle Automation**

```javascript
// ServiceNow Business Rule: AI Alert Processing
(function executeRule(current, previous) {
    
    // Triggered when new event is ready for processing
    if (current.state == 'Ready' && current.type == 'VM Alert') {
        
        // Call AI Agent API
        var request = new sn_ws.RESTMessageV2();
        request.setEndpoint('https://alert-agent.company.local/api/v1/analyze');
        request.setHttpMethod('POST');
        request.setRequestHeader('Content-Type', 'application/json');
        request.setRequestHeader('Authorization', 'Bearer ' + gs.getProperty('ai.agent.token'));
        
        var payload = {
            event_id: current.sys_id.toString(),
            event_number: current.number.toString(),
            priority: 'normal'
        };
        
        request.setRequestBody(JSON.stringify(payload));
        
        var response = request.execute();
        var httpStatus = response.getStatusCode();
        
        if (httpStatus == 200) {
            var responseBody = JSON.parse(response.getBody());
            
            // Create or update incident
            var inc = new GlideRecord('incident');
            inc.initialize();
            inc.setValue('caller_id', gs.getUserID());
            inc.setValue('short_description', 'AI Alert: ' + current.resource.getDisplayValue() + ' - ' + current.type);
            inc.setValue('description', responseBody.executive_summary);
            inc.setValue('urgency', _mapSeverityToUrgency(responseBody.severity));
            inc.setValue('impact', _calculateImpact(responseBody));
            inc.setValue('assignment_group', current.cmdb_ci.support_group);
            inc.setValue('u_ai_analysis_id', responseBody.analysis_id);
            inc.setValue('u_ai_confidence', responseBody.confidence_score);
            inc.setValue('u_recommended_action', responseBody.recommended_action.action_type);
            
            var inc_sys_id = inc.insert();
            
            // Add work note with AI analysis
            inc = new GlideRecord('incident');
            if (inc.get(inc_sys_id)) {
                inc.work_notes = _formatAIAnalysis(responseBody);
                inc.update();
            }
            
            // If auto-remediation recommended and approved, trigger Ansible
            if (responseBody.recommended_action.action_type == 'auto-remediate' && 
                !responseBody.recommended_action.requires_approval) {
                _triggerAnsiblePlaybook(responseBody, inc_sys_id);
            }
            
            // Link event to incident
            current.incident = inc_sys_id;
            current.state = 'Processed';
            current.update();
            
        } else {
            gs.error('AI Agent API call failed: ' + httpStatus);
        }
    }
    
    function _mapSeverityToUrgency(severity) {
        var mapping = {
            'critical': 1,
            'high': 2,
            'medium': 3,
            'low': 4
        };
        return mapping[severity] || 3;
    }
    
    function _calculateImpact(analysis) {
        if (analysis.impact_assessment.critical_impact) {
            return 1; // High impact - critical
        }
        if (analysis.impact_assessment.estimated_affected_users > 100) {
            return 2; // Medium impact
        }
        return 3; // Low impact
    }
    
    function _formatAIAnalysis(analysis) {
        var note = '=== AI ANALYSIS ===\n\n';
        note += 'Confidence Score: ' + (analysis.confidence_score * 100) + '%\n\n';
        note += 'Root Cause: ' + analysis.root_cause_analysis.primary_hypothesis.cause + '\n\n';
        note += 'Evidence:\n';
        analysis.root_cause_analysis.primary_hypothesis.evidence.forEach(function(item) {
            note += '  • ' + item + '\n';
        });
        note += '\nRecommended Action: ' + analysis.recommended_action.action_type + '\n';
        
        if (analysis.recommended_action.immediate_steps.length > 0) {
            note += '\nImmediate Steps:\n';
            analysis.recommended_action.immediate_steps.forEach(function(step) {
                note += '  ' + step.step + '. ' + step.action + '\n';
            });
        }
        
        return note;
    }
    
    function _triggerAnsiblePlaybook(analysis, incident_id) {
        var ansible = new sn_ws.RESTMessageV2();
        ansible.setEndpoint(gs.getProperty('ansible.tower.url') + '/api/v2/job_templates/' + 
                          analysis.ansible_integration.job_template_id + '/launch/');
        ansible.setHttpMethod('POST');
        ansible.setRequestHeader('Authorization', 'Bearer ' + gs.getProperty('ansible.tower.token'));
        ansible.setRequestHeader('Content-Type', 'application/json');
        
        var job_vars = analysis.ansible_integration.extra_vars;
        job_vars.snow_incident_number = incident_id;
        
        ansible.setRequestBody(JSON.stringify({
            extra_vars: job_vars
        }));
        
        var response = ansible.execute();
        
        if (response.getStatusCode() == 201) {
            var job = JSON.parse(response.getBody());
            
            // Update incident with job info
            var inc = new GlideRecord('incident');
            if (inc.get(incident_id)) {
                inc.work_notes = 'Ansible Tower Job launched: ' + job.url;
                inc.u_ansible_job_id = job.id;
                inc.update();
            }
        }
    }
    
})(current, previous);
```

## Deployment Architecture

### Infrastructure Components

```yaml
# Deployment on VMware Infrastructure
components:
  
  ai_agent_application:
    deployment: Docker containers on Kubernetes (VMware Tanzu)
    replicas: 3
    resources:
      cpu: 4 cores
      memory: 16GB
      storage: 100GB SSD
    
    containers:
      - name: alert-ingestion
        image: alert-agent/ingestion:latest
        purpose: ServiceNow event polling and normalization
        
      - name: context-gatherer
        image: alert-agent/context:latest
        purpose: Dynatrace API integration and data enrichment
        
      - name: ai-analyzer
        image: alert-agent/analyzer:latest
        purpose: Claude LLM integration and decision engine
        
      - name: recommendation-engine
        image: alert-agent/recommendations:latest
        purpose: Playbook matching and orchestration
        
      - name: api-gateway
        image: alert-agent/api:latest
        purpose: REST API for ServiceNow integration
        
  database:
    type: PostgreSQL 15
    deployment: VMware Postgres Appliance
    purpose: Historical incident storage, pattern matching
    sizing:
      storage: 500GB
      connections: 100
      
  vector_database:
    type: Pinecone or ChromaDB
    deployment: Managed service or self-hosted
    purpose: Semantic search for similar incidents
    
  message_queue:
    type: RabbitMQ
    deployment: Clustered on Kubernetes
    purpose: Asynchronous alert processing
    
  cache:
    type: Redis
    deployment: Clustered
    purpose: CMDB cache, API response cache

network:
  connectivity:
    - ServiceNow: HTTPS REST API (outbound)
    - Dynatrace: HTTPS API (outbound)
    - Ansible Tower: HTTPS API (outbound)
    - Claude API: HTTPS (outbound via proxy)
    
  security:
    - TLS 1.3 for all communications
    - mTLS for internal service mesh
    - API authentication via OAuth 2.0
    - Secrets managed via HashiCorp Vault

monitoring:
  observability:
    - Dynatrace: Application performance monitoring
    - Prometheus + Grafana: Infrastructure metrics
    - ELK Stack: Centralized logging
    - ServiceNow: Integration health dashboard
    
  slos:
    - Alert processing latency: p95 < 30 seconds
    - API availability: 99.9%
    - LLM response time: p95 < 10 seconds
    - End-to-end MTTA: < 2 minutes
```

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

**Week 1-2: Infrastructure Setup**
- Deploy Kubernetes cluster on VMware Tanzu
- Set up PostgreSQL and Redis instances
- Configure network connectivity and security
- Establish CI/CD pipeline

**Week 3-4: Core Integration**
- Build ServiceNow event polling service
- Implement CMDB enrichment logic
- Create Dynatrace API integration
- Set up Claude API client with retry/fallback

### Phase 2: Intelligence Layer (Weeks 5-8)

**Week 5-6: Analysis Engine**
- Implement pattern matching algorithms
- Build historical incident database
- Create vector database for similarity search
- Develop LLM prompt templates

**Week 7-8: Decision Logic**
- Build classification rules engine
- Implement confidence scoring
- Create recommendation engine
- Develop safety checks and approval workflows

### Phase 3: Automation (Weeks 9-12)

**Week 9-10: Ansible Integration**
- Create Ansible Tower API client
- Build core remediation playbooks
- Implement approval workflow integration
- Set up job monitoring and feedback loop

**Week 11-12: ServiceNow Workflow**
- Build ServiceNow business rules
- Create incident automation workflows
- Implement work note updates
- Configure notifications

### Phase 4: Pilot (Weeks 13-16)

**Week 13-14: Limited Deployment**
- Deploy to non-critical test environment
- Monitor 100 alerts without taking action (shadow mode)
- Validate recommendations against engineer decisions
- Tune confidence thresholds

**Week 15-16: Pilot Production**
- Enable for 5 low-risk applications
- Allow auto-remediation for safe playbooks only
- Gather engineer feedback
- Measure MTTA/MTTR improvements

### Phase 5: Production Rollout (Weeks 17-20)

**Week 17-18: Expand Coverage**
- Add 20 additional applications
- Enable more auto-remediation scenarios
- Integrate with change management
- Train operational teams

**Week 19-20: Full Production**
- Cover all non-critical systems
- Careful expansion to critical systems
- Continuous monitoring and optimization
- Document lessons learned

## Success Metrics

### Operational Metrics

```yaml
kpis:
  efficiency:
    - name: Mean Time to Acknowledge (MTTA)
      baseline: 15 minutes
      target: 2 minutes
      measurement: Time from alert creation to incident assignment
      
    - name: Mean Time to Resolve (MTTR)
      baseline: 4 hours
      target: 2.4 hours (40% reduction)
      measurement: Time from alert to incident resolution
      
    - name: Auto-Resolution Rate
      baseline: 5%
      target: 30%
      measurement: Percentage of alerts resolved without human intervention
      
  quality:
    - name: False Positive Rate
      target: <5%
      measurement: Incorrect recommendations / total recommendations
      
    - name: Recommendation Acceptance Rate
      target: >80%
      measurement: Recommendations followed / total recommendations
      
    - name: Root Cause Accuracy
      target: >85%
      measurement: Correct root cause identified / total incidents
      
  business_impact:
    - name: Engineering Time Saved
      target: 20 hours/week
      measurement: Time saved on alert triage and investigation
      
    - name: Reduced Alert Fatigue
      target: 50% reduction in manual alert reviews
      measurement: Engineer feedback and time tracking
      
    - name: Improved Patient Care Availability
      target: 99.95% uptime for critical systems
      measurement: System availability monitoring
```

### Dashboard Example

```
┌─────────────────────────────────────────────────────────────────┐
│          Alert Intelligence Agent - Operations Dashboard         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Last 24 Hours                                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                  │
│  📊 Alerts Processed: 247                                        │
│      • CPU: 89  • Memory: 103  • Storage: 55                    │
│                                                                  │
│  🤖 Auto-Resolved: 74 (30%)                                      │
│      • Log rotation: 32                                          │
│      • Temp file cleanup: 18                                     │
│      • Cache flush: 12                                           │
│      • Suppressed (known pattern): 12                            │
│                                                                  │
│  👨‍💻 Guided Remediation: 156 (63%)                                │
│      • Service restarts: 45                                      │
│      • Investigation needed: 89                                  │
│      • Capacity review: 22                                       │
│                                                                  │
│  🚨 Escalated: 17 (7%)                                           │
│      • Critical severity: 8                                      │
│      • Unknown pattern: 5                                        │
│      • Requires emergency CAB: 4                                 │
│                                                                  │
│  ⚡ Performance                                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                  │
│  Average Processing Time: 18 seconds                             │
│  MTTA: 1.8 minutes  (target: <2m)  ✓                            │
│  MTTR: 2.9 hours    (target: <2.4h) ⚠                           │
│                                                                  │
│  🎯 AI Confidence Distribution                                   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                  │
│  High (>80%):   ████████████████████ 68%                        │
│  Medium (60-80%): ████████ 22%                                   │
│  Low (<60%):    ██ 10%                                           │
│                                                                  │
│  ✅ Recommendation Acceptance: 84%                               │
│                                                                  │
│  Top Root Causes Identified:                                     │
│  1. Memory leak (Java)           - 34 incidents                  │
│  2. Log file growth              - 28 incidents                  │
│  3. Backup job CPU spike         - 19 incidents                  │
│  4. Database connection pool     - 12 incidents                  │
│  5. Antivirus scan               - 8 incidents                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Security & Compliance

### Healthcare Compliance Considerations

```yaml
compliance:
  hipaa:
    - requirement: Audit trail for all automated actions
      implementation: All decisions logged to immutable audit log
      
    - requirement: Access controls for PHI systems
      implementation: Role-based access control, separation of duties
      
    - requirement: Encryption at rest and in transit
      implementation: TLS 1.3, AES-256 encryption for storage
      
  sox:
    - requirement: Change management for financial systems
      implementation: All changes require approval workflow
      
    - requirement: Separation of duties
      implementation: AI cannot approve its own recommendations
      
  internal_policies:
    - requirement: critical system changes require CAB approval
      implementation: Auto-remediation disabled for critical, workflow enforces CAB
      
    - requirement: Maintenance window compliance
      implementation: Schedule-aware, respects maintenance calendar
      
security:
  authentication:
    - ServiceNow: OAuth 2.0 service account
    - Dynatrace: API token with read-only permissions
    - Ansible Tower: Service account with job launch permissions
    - Claude API: Anthropic API key (rotated quarterly)
    
  authorization:
    - Principle of least privilege
    - No direct VM access (all via Ansible)
    - Read-only access to monitoring systems
    - Write access only to incident records
    
  data_protection:
    - No PHI stored in AI system
    - PII scrubbed from logs
    - Sensitive credentials in Vault
    - Encrypted backups
```

## Cost Analysis

```yaml
estimated_costs:
  
  infrastructure:
    compute:
      - VMware vCPU: 12 cores @ $150/month = $1,800/month
      - Memory: 48GB @ $50/GB/month = $2,400/month
      - Storage: 1TB SSD @ $200/month = $200/month
    subtotal: $4,400/month
    
  software_licenses:
    - Dynatrace: Existing license (no additional cost)
    - Ansible Tower: Existing license (no additional cost)
    - ServiceNow: Existing license (no additional cost)
    - Claude API: ~$50-200/month (based on usage)
    - Vector DB: $200/month (managed service)
    subtotal: $250-400/month
    
  development:
    - Initial build: 4 engineers × 5 months = 20 person-months
    - Ongoing maintenance: 0.5 FTE
    
  total_monthly_opex: ~$5,000/month
  
  roi_analysis:
    time_saved:
      - 20 hours/week engineer time saved
      - Average loaded cost: $80/hour
      - Annual savings: 20 × 52 × $80 = $83,200
      
    incident_reduction:
      - Faster resolution reduces impact
      - Estimated value: $50,000/year
      
    total_annual_benefit: ~$133,000
    payback_period: 9 months
```

## Risk Mitigation

```yaml
risks:
  
  - risk: AI makes incorrect recommendation leading to outage
    likelihood: Medium
    impact: High
    mitigation:
      - Confidence thresholds for auto-remediation
      - Human-in-the-loop for critical systems
      - Comprehensive testing in non-production
      - Immediate rollback capability
      - Incident review process
      
  - risk: Integration failure with ServiceNow/Dynatrace/Ansible
    likelihood: Medium
    impact: Medium
    mitigation:
      - Graceful degradation (manual mode)
      - API health monitoring
      - Redundant connectivity
      - Comprehensive error handling
      - Runbook for manual failover
      
  - risk: Claude API unavailable or rate-limited
    likelihood: Low
    impact: Medium
    mitigation:
      - Fallback to rule-based engine
      - Request queuing and retry logic
      - Caching of common patterns
      - Alert ops team if degraded
      
  - risk: Compliance violation (unauthorized change to critical system)
    likelihood: Low
    impact: Critical
    mitigation:
      - Hard-coded critical system protection
      - Approval workflow enforcement
      - Comprehensive audit logging
      - Regular compliance reviews
      
  - risk: Alert fatigue from false positives
    likelihood: Medium
    impact: Medium
    mitigation:
      - Continuous tuning of confidence thresholds
      - Feedback loop from engineers
      - Pattern learning from false positives
      - Suppression rules for known patterns
```

## Next Steps

### Immediate Actions (This Month)

1. **Stakeholder Alignment**
   - Present design to Infrastructure leadership
   - Get CAB approval for pilot
   - Identify 5 pilot applications
   - Secure budget approval

2. **Technical Preparation**
   - Audit Ansible Tower playbook inventory
   - Document current alert patterns
   - Set up development environment
   - Create ServiceNow development instance

3. **Team Readiness**
   - Assign development team
   - Schedule architecture review
   - Plan training for operations team
   - Establish success metrics

### Questions to Address

1. What is the preferred vector database (Pinecone vs self-hosted ChromaDB)?
2. Should we integrate with existing PagerDuty or use ServiceNow exclusively?
3. What is the approval process for AI-driven changes to critical systems?
4. Are there specific compliance requirements beyond HIPAA/SOX?
5. What is the disaster recovery plan if AI agent is unavailable?

---

**Document Version:** 1.0  
**Last Updated:** February 8, 2024  
**Author:** AI Architecture Team  
**Status:** Proposed Design - Pending Review
