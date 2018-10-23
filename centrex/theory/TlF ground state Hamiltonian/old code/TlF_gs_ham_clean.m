%this program calculates the eigenenergies & eigenstates 
%of the TlF groundstate
tic %starts clock
Jmax = 6;   %Max J value in Hamiltonian
I_Tl = 1/2;     %Setting up constants...this is I1 in Ramsey's notation
I_F = 1/2;    %Setting up constants...this is I2 in Ramsey's notation
N_states = (2*I_Tl+1)*(2*I_F+1)*(Jmax+1)^2;  %Total number of states in Hilbert space considered
QN = make_QN(Jmax,I_F,I_Tl, N_states); %make an array of quantum numbers for each basis state (|J m_J m_I_Tl m_I_F>)
%
%csvwrite('test1.dat',QN);  %write array of quantum numbers 
%
%generate field-free Hamiltonian
%H = Brot(J.J) + c1(I1.J) + c2(I2.J) + c4(I1.I2) +
%5c3[3(I1.J)(I2.J)+3(I2.J)(I1.J)-2(I1.I2)J.J]/[(2J+3)(2J-1)]
%set up constants for field-free Hamiltonian.  Everything in Hz.
% Data from D.A. Wilkening, N.F. Ramsey, and D.J. Larson, Phys Rev A 29,
% 425 (1984).
%
%Set up parameters for simulation
%Brot = 6686667000; %This Brot is from Eric's rovibrational branching paper
Brot = 6689920000; %From Ramsay
%Drot = 10869; %from Eric's paper, for 2nd order correction to rotational energy
c1 = 126030; %c1 =0; %
c2 = 17890; %c2 = 0; %
c3 = 5/2*700; %c3 = 0; %
%c3 = 100000;
c4 = -13300; %c4 = 0; %
u_e = 4.2282;

%claculate dipole moment of TlF from u_e
D_TlF = u_e * 0.393430307 *5.291772e-9/4.135667e-15;


%Generate all parts of the Hamiltonian (see function for details)
%[Ham_rot, Ham_sr,Ham_ss_1, Ham_ss_2, Ham_St_z, Ham_Z_z] = make_TlF_gs_ham(Jmax,I_Tl,I_F,Brot,c1,c2,c3,c4,u_e,QN);
[Ham_rot, Ham_c1,Ham_c2, Ham_c3,Ham_c4, Ham_St_z, Ham_Z_z] = make_TlF_gs_ham_new_c3(Jmax,I_Tl,I_F,QN);


%generate eigenvectors and eigenvalues that will be used to sort the
%output of eig correctly
[V_R, D_R] = make_V_ramsey(Ham_rot, Ham_c1, Ham_c2,Ham_c3, Ham_c4, Ham_St_z, Ham_Z_z);

%
% hfs_mat is a 1-D array to store energies for a given value of Ez, Bz
hfs_mat = zeros(N_states,1);
hfs_0_mat = zeros(N_states,1);
Bz = 18.4; %Bz in Gauss
%
% loop over different values of Ez
nEz_max = 100; 
Ez_max = 70; %in V/cm

n_count = 0; %number to keep index arrays
%loop to figure out number of entries needed into the arrays 
for nEz = 0:nEz_max
    if nEz > 200 && nEz < 29800 
        if nEz > 20200 || nEz < 19800 && mod(nEz,1000) ~= 0
            continue
        end
    end
    n_count = n_count + 1;
end
n_max = n_count;

%initialise some arrays
Energies = zeros(n_max,12);  %this is an array to store energies of J=1 states only, for all values of Ez in loop
Energies_0 = zeros(n_max,12);  %this is an array to store energies of J=1 states only, for all values of Ez in loop
Energies_all = zeros(n_max,N_states); %array to store energies of all states
Ez_array = zeros(n_max,1);  %this is an array of all the Ez values in the loop
V_prev = zeros(N_states); %array to store the V matrix of the previous iteration. Use this to make sure state vectors stay in the same order throughout.
V_0_prev = zeros(N_states); %as above but for V_0
D_prev = zeros(N_states,1); %as above but for D
D_0_prev = zeros(N_states,1);

%rezero n_count so can use it to index the arrays
n_count = 0;

%start loop over different E field values and calculate energies and state
%vectors
for nEz = 0:nEz_max
    Ez = nEz*Ez_max/nEz_max;  %set the Ez value for this iteration of the loop
    if nEz > 200 && nEz < 29500 
        if nEz > 20200 || nEz < 19800 && mod(nEz,1000) ~= 0
            continue
        end
    end
    n_count = n_count + 1;
    
    %some limits needed for plotting
    if nEz == 29800
        n_hi_low = n_count;
    end
    if nEz == 30200
        n_hi_hi = n_count;
    end
    
    if nEz == 19800
        n_20kV_low = n_count;
    end
    if nEz == 20200
        n_20kV_hi = n_count;
    end
    
    Ez_array(n_count,1) = Ez;  %fill in the array of Ez values
    Ham = Brot*Ham_rot + Bz*Ham_Z_z + Ez*D_TlF*Ham_St_z + c3*Ham_c3 + c4*Ham_c4 + c1 * Ham_c1 + c2 * Ham_c2;
    [V,D] = eig(Ham,'vector');        %find eigenvalues D and eigenvectors V of Hamiltonian
    
    %Define H_0 and find evecs and evals (can use H_0 to leave out some
    %parts of the Hamiltonian)
    Ham_0 = Brot*Ham_rot + Bz*Ham_Z_z + Ez*D_TlF*Ham_St_z + c3*Ham_c3 + c4*Ham_c4 + c1 * Ham_c1 + c2 * Ham_c2;
    [V_0, D_0] = eig(Ham_0,'vector');
        
    if nEz == 0
        %sort the output from eig
        [V,D] = custom_sort(V,D,V_R,D_R);
        %order evecs and evals of H_0 in so that V_0 is diagonal at first
        D_I = zeros(N_states,1);
        for i=1:N_states
            J_i = QN(i,1);
            D_I(i,1) = J_i*(J_i +1)*Brot;
        end
        [V_0,D_0] = custom_sort(V_0,D_0,eye(N_states),D_I);
    end
        
    
    if nEz > 0
        %for nEz > 0 do the sorting based on the previous (sorted)
        %eigenvector and eigenvalues matrices
        [V,D] = custom_sort(V,D,V_prev,D_prev);
        [V_0,D_0] = custom_sort(V_0,D_0,V_0_prev,D_0_prev);
    end
    
    V_prev = V; %store previous state vector array so can compare indices of different states in next eigenvalue computation
    D_prev = D;
    V_0_prev = V_0;
    D_0_prev = D_0;
    
    %subtract away rotational energy for easier viewing of substructure
    for i=1:N_states
        J_i = QN(i,1);
        hfs_mat(i,1) = D(i) - J_i*(J_i +1)*Brot; %subtract rotational energy
        hfs_0_mat(i,1) = D_0(i) - J_i*(J_i +1)*Brot; %subtract rotational energy
    end
    hfs_kHz = hfs_mat/1000; %change units to kHz for easier viewing
    hfs_0_kHz = hfs_0_mat/1000;
    Energies(n_count,:) = hfs_kHz(5:16);  %fill in array of energies of J=1 states only, with one row for each value of Ezin loop
    Energies_0(n_count,:) = hfs_0_kHz(5:16);
    Energies_all(n_count,:) = D_0; 
end

%%%Plotting stuff below%%%%%
figure
plot(Ez_array,Energies);  %plot the energies of the J=1 states vs. Ez
axis([0 80 -300 300]);  %set the axis limits to match the plot in Ramsey's paper
leg = zeros(12,1);
for i = 1:12
    leg(i,:) = i;
end
leg = num2str(leg);
legend(leg)
xlabel('Electric field / V/cm')
ylabel('Energy shift / kHz')
title('Stark shift for the J = 1 states in groundstate of TlF (B = 18.4G)')

figure
plot(Ez_array,Energies);  %plot the energies of the J=1 states vs. Ez
leg = zeros(12,1);
for i = 1:12
    leg(i,:) = i;
end
leg = num2str(leg);
legend(leg)

figure
axis([0 80 -300 300]);  %set the axis limits to match the plot in Ramsey's paper
hold on
plot(Ez_array,Energies(:,3))
plot(Ez_array,Energies(:,8))
plot(Ez_array,Energies(:,2))
plot(Ez_array,Energies(:,5))
legend('j','e','k','h')
xlabel('Electric field / V/cm ')
ylabel('Energy shift / kHz')
hold off

% figure
% axis([0 80 -300 300]);  %set the axis limits to match the plot in Ramsey's paper
% hold on
% plot(Ez_array,Energies_0(:,3))
% plot(Ez_array,Energies_0(:,1))
% plot(Ez_array,Energies_0(:,10))
% plot(Ez_array,Energies_0(:,12))
% legend('j','e','k','h')
% xlabel('Electric field / V/cm ')
% ylabel('Energy shift / kHz')
% hold off

% figure
% hold on
% plot(Ez_array,Energies(:,3))
% plot(Ez_array,Energies(:,8))
% plot(Ez_array,Energies(:,2))
% plot(Ez_array,Energies(:,5))
% plot(Ez_array,Energies_0(:,3),'--')
% plot(Ez_array,Energies_0(:,1),'--')
% plot(Ez_array,Energies_0(:,10),'--')
% plot(Ez_array,Energies_0(:,12),'--')
% legend('j','e','k','h','j_0','e_0','k_0','h_0')
% xlabel('Electric field / V/cm ')
% ylabel('Energy shift / kHz')
% xlim([29800 30200])
% hold off




% figure
% hold on
% plot(Ez_array,Energies_0);  %plot the energies of the J=1 states vs. Ez

figure
hold on
plot(Ez_array,Energies_all);  %plot the energies of the J=1 states vs. Ez



toc %stop clock