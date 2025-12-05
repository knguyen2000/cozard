import os
import time
import json
from ipaddress import IPv4Network
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager

fab_dir = os.path.expanduser('~/.fabric')
os.makedirs(fab_dir, exist_ok=True)

os.environ['FABRIC_TOKEN_LOCATION'] = os.path.join(fab_dir, 'id_token.json')
os.environ['FABRIC_BASTION_KEY_LOCATION'] = os.path.join(fab_dir, 'bastion_key')
os.environ['FABRIC_SLICE_PRIVATE_KEY_FILE'] = os.path.join(fab_dir, 'slice_key')
os.environ['FABRIC_SLICE_PUBLIC_KEY_FILE'] = os.path.join(fab_dir, 'slice_key.pub')

os.environ['FABRIC_LOG_LEVEL'] = os.environ.get('FABRIC_LOG_LEVEL', 'CRITICAL')
os.environ['FABRIC_QUIET'] = 'True'

def provision_slice(slice_name="cloud_gaming_experiment", experiment_type="gaming"):
    """
    Provision FABRIC slice for experiments
    
    Args:
        slice_name: Name of the slice
        experiment_type: 'crux' (3 nodes) or 'gaming' (4 nodes)
    """
    fablib = fablib_manager()
    
    try:
        slice = fablib.get_slice(name=slice_name)
        print(f"Slice {slice_name} already exists. Deleting...")
        slice.delete()
        time.sleep(10)
    except:
        pass

    print(f"Creating slice {slice_name}...")
    slice = fablib.new_slice(name=slice_name)

    # Constraints
    CORES = 2
    RAM = 10
    DISK = 10  # Max allowed without VM.NoLimitDisk tag
    IMAGE = 'default_ubuntu_20'
    SITE = 'SALT'  # Force all nodes to same site (L2 networks limited to 2 sites)

    if experiment_type == "gaming":
        # Cloud Gaming Kill-Switch Experiment (4 nodes)
        print("Topology: Cloud Gaming Experiment (4 nodes)")
        
        # Node A: Gamer/Sender (GPU)
        print("Adding Gamer A (GPU sender)...")
        gamer_a = slice.add_node(name='gamer-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        gamer_a.add_component(model='GPU_TeslaT4', name='gpu1')
        iface_a = gamer_a.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # Node B: Receiver/Monitor (GPU)
        print("Adding Receiver B (GPU receiver)...")
        receiver_b = slice.add_node(name='receiver-b', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        receiver_b.add_component(model='GPU_TeslaT4', name='gpu1')
        iface_b = receiver_b.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # Node C: Router/Signaling
        print("Adding Router C...")
        router_c = slice.add_node(name='router-c', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        iface_c = router_c.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # Node D: Attacker
        print("Adding Attacker D...")
        attacker_d = slice.add_node(name='attacker-d', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        iface_d = attacker_d.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # L2 Network
        print("Creating L2 Network...")
        net = slice.add_l2network(name='gaming_net', interfaces=[iface_a, iface_b, iface_c, iface_d])

    else:
        # CRUX Testbed (3 nodes) - original topology
        print("Topology: CRUX Testbed (3 nodes)")
        
        # Worker A
        print("Adding Worker A...")
        worker_a = slice.add_node(name='worker-a', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        worker_a.add_component(model='GPU_TeslaT4', name='gpu1')
        iface_a = worker_a.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # Worker B
        print("Adding Worker B...")
        worker_b = slice.add_node(name='worker-b', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        worker_b.add_component(model='GPU_TeslaT4', name='gpu1')
        iface_b = worker_b.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # Scheduler C
        print("Adding Scheduler C...")
        scheduler_c = slice.add_node(name='scheduler-c', site=SITE, cores=CORES, ram=RAM, disk=DISK, image=IMAGE)
        iface_c = scheduler_c.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]

        # L2 Network
        print("Creating L2 Network...")
        net = slice.add_l2network(name='crux_net', interfaces=[iface_a, iface_b, iface_c])

    # Submit
    print("Submitting slice request...")
    slice.submit()

    # Configure Network
    print("Configuring Network...")
    
    if experiment_type == "gaming":
        # Gaming topology IPs
        iface_a = slice.get_node('gamer-a').get_interface(network_name='gaming_net')
        iface_a.ip_addr_add(addr='192.168.10.10', subnet=IPv4Network('192.168.10.0/24'))
        iface_a.ip_link_up()

        iface_b = slice.get_node('receiver-b').get_interface(network_name='gaming_net')
        iface_b.ip_addr_add(addr='192.168.10.11', subnet=IPv4Network('192.168.10.0/24'))
        iface_b.ip_link_up()

        iface_c = slice.get_node('router-c').get_interface(network_name='gaming_net')
        iface_c.ip_addr_add(addr='192.168.10.12', subnet=IPv4Network('192.168.10.0/24'))
        iface_c.ip_link_up()

        iface_d = slice.get_node('attacker-d').get_interface(network_name='gaming_net')
        iface_d.ip_addr_add(addr='192.168.10.13', subnet=IPv4Network('192.168.10.0/24'))
        iface_d.ip_link_up()

        print("Slice provisioning complete.")
        
        # Save details
        details = {
            "gamer-a": str(slice.get_node('gamer-a').get_management_ip()),
            "receiver-b": str(slice.get_node('receiver-b').get_management_ip()),
            "router-c": str(slice.get_node('router-c').get_management_ip()),
            "attacker-d": str(slice.get_node('attacker-d').get_management_ip())
        }
    else:
        # CRUX topology IPs
        iface_a = slice.get_node('worker-a').get_interface(network_name='crux_net')
        iface_a.ip_addr_add(addr='192.168.10.10', subnet=IPv4Network('192.168.10.0/24'))
        iface_a.ip_link_up()

        iface_b = slice.get_node('worker-b').get_interface(network_name='crux_net')
        iface_b.ip_addr_add(addr='192.168.10.11', subnet=IPv4Network('192.168.10.0/24'))
        iface_b.ip_link_up()

        iface_c = slice.get_node('scheduler-c').get_interface(network_name='crux_net')
        iface_c.ip_addr_add(addr='192.168.10.12', subnet=IPv4Network('192.168.10.0/24'))
        iface_c.ip_link_up()

        print("Slice provisioning complete.")
        
        # Save details
        details = {
            "worker-a": str(slice.get_node('worker-a').get_management_ip()),
            "worker-b": str(slice.get_node('worker-b').get_management_ip()),
            "scheduler-c": str(slice.get_node('scheduler-c').get_management_ip())
        }
    
    with open("slice_details.json", "w") as f:
        json.dump(details, f)

if __name__ == "__main__":
    import sys
    exp_type = sys.argv[1] if len(sys.argv) > 1 else "gaming"
    provision_slice(experiment_type=exp_type)

