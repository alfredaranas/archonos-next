# Ultrasound Physics Diagrams

Collection of Mermaid diagrams for sonography learning.

---

## Ultrasound Wave Propagation

```mermaid
flowchart TD
    A[Transducer] -->|Electrical Pulse| B[Piezoelectric Crystal]
    B -->|Sound Wave| C[Soft Tissue]
    C -->|Reflection| D[Echo]
    D -->|Sound Wave| B
    B -->|Electrical Signal| E[Display Processor]
    E --> F[Ultrasound Image]
    
    style A fill:#00d9ff
    style F fill:#00ff88
```

---

## Artifact Types

```mermaid
flowchart LR
    subgraph Real[Real Anatomy]
        R1[Tissue Boundary]
    end
    
    subgraph Artifact[Artifacts]
        A1[Reverberation]
        A2[Mirror]
        A3[Ring Down]
        A4[Comet Tail]
    end
    
    R1 -->|Misinterpretation| A1
    R1 -->|Reflection| A2
    R1 -->|Fluid Bubbles| A3
    R1 -->|Multiple Reflections| A4
    
    style Real fill:#00ff88,color:#000
    style Artifact fill:#ff6464,color:#000
```

---

## Ultrasound Beam Types

```mermaid
flowchart TB
    subgraph Near[Near Field / Fresnel]
        D1[Parallel Rays]
    end
    
    subgraph Far[Far Field / Fraunhofer]
        D2[Diverging Rays]
    end
    
    T[Transducer] --> D1
    D1 --> D2
    
    style Near fill:#00d9ff,color:#000
    style Far fill:#302b63,color:#fff
```

---

## Image Formation Process

```mermaid
flowchart TD
    A[Pulse] --> B[Transmit]
    B --> C[Receive]
    C --> D[Process]
    D --> E[Display]
    
    style A fill:#00d9ff
    style E fill:#00ff88
```

---

## Learning Path: Ultrasound Physics

```mermaid
graph TD
    Basics[Basic Physics] --> |5.2 min| Beam[Beam Formation]
    Beam --> |10.4 min| Interaction[Tissue Interaction]
    Interaction --> |17.6 min| Artifacts[Artifacts]
    Artifacts --> |7.8 min| Advanced[Advanced Concepts]
    
    Basics --> |15.1 min| Lecture[Physics Lecture]
    Lecture --> |22.4 min| ImageGen[Image Generation]
    
    style Basics fill:#00ff88,color:#000
    style Artifacts fill:#00d9ff,color:#000
    style Advanced fill:#ff6464,color:#000
```

---

## Cost Comparison

```mermaid
pie
    title Sonography Education Costs
    "Traditional School ($40k+)" : 65
    "Online Courses ($2k)" : 25
    "AI-Powered Learning ($200)" : 10
```

---

## ARDMS Exam Prep

```mermaid
graph LR
    S1[Prerequisite Courses] --> S2[Submit Application]
    S2 --> S3[Pass SPI Exam]
    S3 --> S4[Pass specialty Exam]
    S4 --> S5[Registry Number]
    
    style S1 fill:#302b63,color:#fff
    style S5 fill:#00ff88,color:#000
```

---

## Quick Reference: Artifact Causes

```mermaid
mindmap
  root((Artifacts))
    Reverberation
      Multiple reflectors
      Strong reflector
      Near probe
    Mirror
      Strong reflector
      Angle > 45 deg
      Opposite side
    Ring Down
      Microbubbles
      Fluid pockets
      Comet tail similar
    Side Lobe
      Beam side lobes
      Off-axis reflectors
      Ghost images
```

---

## Equipment Setup

```mermaid
flowchart LR
    subgraph Probe[Transducer]
        P1[Housing]
        P2[Crystal]
        P3[Matching Layer]
    end
    
    subgraph System[Processing]
        S1[Beam Former]
        S2[Image Processor]
        S3[Display]
    end
    
    Probe --> System
    
    style Probe fill:#00d9ff,color:#000
    style System fill:#302b63,color:#fff
```